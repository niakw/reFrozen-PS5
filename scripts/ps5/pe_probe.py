#!/usr/bin/env python3
"""Read-only PE metadata/import fingerprinting for user-owned Warcraft III installs.

The probe never executes a PE. Reports contain the basename, SHA-256, architecture,
image metadata and imported DLL/API names. A Warcraft patch version is only assigned
after a separately verified exact-hash catalog exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_PE_OFFSET = 1024 * 1024
MAX_SECTIONS = 96
MAX_IMPORT_DESCRIPTORS = 4096
MAX_IMPORTS_PER_DLL = 100_000
MAX_EXPORTS = 100_000
MAX_STRING = 4096
_MACHINE = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "arm64"}

_RUNTIME_DLL_AREAS = {
    "core": {
        "kernel32.dll", "kernelbase.dll", "ntdll.dll", "advapi32.dll",
        "shell32.dll", "shlwapi.dll", "version.dll", "userenv.dll",
    },
    "window_input": {
        "user32.dll", "gdi32.dll", "imm32.dll", "dinput.dll", "dinput8.dll",
        "xinput1_1.dll", "xinput1_2.dll", "xinput1_3.dll", "xinput1_4.dll",
        "xinput9_1_0.dll",
    },
    "graphics": {
        "opengl32.dll", "ddraw.dll", "d3d8.dll", "d3d9.dll", "d3d10.dll",
        "d3d10_1.dll", "d3d11.dll", "d3d12.dll", "dxgi.dll",
    },
    "audio": {
        "winmm.dll", "dsound.dll", "xaudio2_7.dll", "xaudio2_8.dll",
        "xaudio2_9.dll", "avrt.dll",
    },
    "network": {
        "wsock32.dll", "ws2_32.dll", "mswsock.dll", "wininet.dll",
        "winhttp.dll", "iphlpapi.dll", "dnsapi.dll",
    },
    "com_media": {
        "ole32.dll", "oleaut32.dll", "uuid.dll", "quartz.dll", "strmiids.dll",
        "mf.dll", "mfplat.dll", "mfreadwrite.dll", "wmvcore.dll",
    },
    "runtime": {
        "msvcrt.dll", "ucrtbase.dll", "vcruntime140.dll", "vcruntime140_1.dll",
        "msvcp140.dll",
    },
}


class PEFormatError(ValueError):
    """Unsupported or malformed portable executable."""


def _slice(raw: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(raw) or size > len(raw) - offset:
        raise PEFormatError(f"truncated {label}")
    return raw[offset:offset + size]


def _cstring(raw: bytes, offset: int, label: str) -> str:
    if not 0 <= offset < len(raw):
        raise PEFormatError(f"invalid {label} offset")
    end = raw.find(b"\0", offset, min(len(raw), offset + MAX_STRING))
    if end < 0:
        raise PEFormatError(f"unterminated {label}")
    return raw[offset:end].decode("ascii", "replace")


def _runtime_area(dll: str) -> str:
    name = dll.lower()
    for area, dlls in _RUNTIME_DLL_AREAS.items():
        if name in dlls:
            return area
    return "unknown"


def _graphics_profile(imports: list[dict]) -> dict:
    """Classify only statically imported graphics DLLs.

    Games may LoadLibrary a renderer later, so absence here is never proof
    that a backend is unsupported or unused.
    """
    dlls = {item["dll_normalized"] for item in imports}
    detected = []
    for backend, names in (
        ("opengl", {"opengl32.dll"}),
        ("directdraw", {"ddraw.dll"}),
        ("direct3d8", {"d3d8.dll"}),
        ("direct3d9", {"d3d9.dll"}),
        ("direct3d10", {"d3d10.dll", "d3d10_1.dll"}),
        ("direct3d11", {"d3d11.dll", "dxgi.dll"}),
        ("direct3d12", {"d3d12.dll", "dxgi.dll"}),
    ):
        matched = sorted(dlls & names)
        if matched:
            detected.append({"backend": backend, "dlls": matched})

    if any(item["backend"] == "opengl" for item in detected):
        ps5_initial_route = "opengl_wgl_to_ps5_egl"
    elif detected:
        ps5_initial_route = "renderer_translation_or_runtime_forcing_required"
    else:
        ps5_initial_route = "undetermined_dynamic_renderer_possible"

    return {
        "static_backends": detected,
        "ps5_initial_route": ps5_initial_route,
        "confidence": "imports_only",
        "note": (
            "Static imports are evidence only; runtime LoadLibrary/GetProcAddress "
            "or command-line renderer selection can change the active backend."
        ),
    }


def _rva_to_offset(rva: int, sections: list[dict], size_of_headers: int, raw_size: int) -> int:
    if rva < size_of_headers:
        if rva >= raw_size:
            raise PEFormatError("header RVA outside file")
        return rva
    for section in sections:
        start = section["virtual_address"]
        span = max(section["virtual_size"], section["raw_size"])
        if start <= rva < start + span:
            delta = rva - start
            if delta >= section["raw_size"]:
                raise PEFormatError("RVA points into zero-fill section tail")
            offset = section["raw_offset"] + delta
            if offset >= raw_size:
                raise PEFormatError("RVA maps outside file")
            return offset
    raise PEFormatError(f"unmapped RVA 0x{rva:x}")


def _parse_exports(raw: bytes, bits: int, optional: bytes, sections: list[dict],
                   size_of_headers: int) -> list[dict]:
    dir_count_off = 92 if bits == 32 else 108
    dir_base = 96 if bits == 32 else 112
    if len(optional) < dir_count_off + 4:
        return []
    count = struct.unpack_from("<I", optional, dir_count_off)[0]
    if count == 0 or len(optional) < dir_base + 8:
        return []
    export_rva, export_size = struct.unpack_from("<II", optional, dir_base)
    if not export_rva or not export_size:
        return []
    directory_offset = _rva_to_offset(export_rva, sections, size_of_headers, len(raw))
    directory = _slice(raw, directory_offset, 40, "export directory")
    (_, _, _, _, name_rva, ordinal_base, function_count, name_count,
     functions_rva, names_rva, ordinals_rva) = struct.unpack("<IIHHIIIIIII", directory)
    if function_count > MAX_EXPORTS or name_count > MAX_EXPORTS:
        raise PEFormatError("too many exports")
    if function_count == 0:
        return []
    functions_offset = _rva_to_offset(functions_rva, sections, size_of_headers, len(raw))
    functions = struct.unpack(
        f"<{function_count}I",
        _slice(raw, functions_offset, function_count * 4, "export address table"),
    )
    names_by_index: dict[int, str] = {}
    if name_count:
        names_offset = _rva_to_offset(names_rva, sections, size_of_headers, len(raw))
        ordinals_offset = _rva_to_offset(ordinals_rva, sections, size_of_headers, len(raw))
        name_rvas = struct.unpack(
            f"<{name_count}I",
            _slice(raw, names_offset, name_count * 4, "export name pointers"),
        )
        ordinals = struct.unpack(
            f"<{name_count}H",
            _slice(raw, ordinals_offset, name_count * 2, "export ordinals"),
        )
        for name_ptr, index in zip(name_rvas, ordinals):
            if index >= function_count:
                raise PEFormatError("export name ordinal outside function table")
            names_by_index[index] = _cstring(
                raw, _rva_to_offset(name_ptr, sections, size_of_headers, len(raw)),
                "export symbol",
            )
    exports = []
    export_end = export_rva + export_size
    for index, function_rva in enumerate(functions):
        if function_rva == 0:
            continue
        ordinal = ordinal_base + index
        forwarder = None
        if export_rva <= function_rva < export_end:
            forwarder = _cstring(
                raw, _rva_to_offset(function_rva, sections, size_of_headers, len(raw)),
                "export forwarder",
            )
        exports.append({
            "name": names_by_index.get(index),
            "ordinal": ordinal,
            "rva": f"0x{function_rva:x}",
            "forwarder": forwarder,
        })
    return exports


def _parse_imports(raw: bytes, bits: int, optional: bytes, sections: list[dict],
                   size_of_headers: int) -> list[dict]:
    dir_count_off = 92 if bits == 32 else 108
    dir_base = 96 if bits == 32 else 112
    if len(optional) < dir_count_off + 4:
        return []
    count = struct.unpack_from("<I", optional, dir_count_off)[0]
    if count <= 1 or len(optional) < dir_base + 16:
        return []
    import_rva, import_size = struct.unpack_from("<II", optional, dir_base + 8)
    if not import_rva or not import_size:
        return []
    descriptor_offset = _rva_to_offset(import_rva, sections, size_of_headers, len(raw))
    imports = []
    max_descriptors = min(MAX_IMPORT_DESCRIPTORS, max(1, import_size // 20 + 1))
    thunk_size = 4 if bits == 32 else 8
    ordinal_bit = 1 << (31 if bits == 32 else 63)
    unpack_thunk = "<I" if bits == 32 else "<Q"

    for index in range(max_descriptors):
        off = descriptor_offset + index * 20
        descriptor = _slice(raw, off, 20, "import descriptor")
        oft, timestamp, forwarder, name_rva, first_thunk = struct.unpack("<IIIII", descriptor)
        if not any((oft, timestamp, forwarder, name_rva, first_thunk)):
            break
        if not name_rva or not first_thunk:
            raise PEFormatError("malformed import descriptor")
        dll = _cstring(raw, _rva_to_offset(name_rva, sections, size_of_headers, len(raw)),
                       "import DLL name")
        thunk_rva = oft or first_thunk
        thunk_offset = _rva_to_offset(thunk_rva, sections, size_of_headers, len(raw))
        symbols = []
        for slot in range(MAX_IMPORTS_PER_DLL):
            value = struct.unpack(unpack_thunk,
                                  _slice(raw, thunk_offset + slot * thunk_size,
                                         thunk_size, "import thunk"))[0]
            if value == 0:
                break
            if value & ordinal_bit:
                symbols.append(f"#{value & 0xffff}")
            else:
                name_offset = _rva_to_offset(value, sections, size_of_headers, len(raw))
                _slice(raw, name_offset, 2, "import hint")
                symbols.append(_cstring(raw, name_offset + 2, "import symbol"))
        else:
            raise PEFormatError("too many imports in one DLL")
        imports.append({
            "dll": dll,
            "dll_normalized": dll.lower(),
            "runtime_area": _runtime_area(dll),
            "count": len(symbols),
            "symbols": symbols,
        })
    else:
        raise PEFormatError("too many import descriptors")
    return imports


def inspect_pe(path: Path) -> dict:
    """Parse PE headers/imports without loading or executing guest code."""
    path = Path(path)
    raw = path.read_bytes()
    dos = _slice(raw, 0, 64, "DOS header")
    if dos[:2] != b"MZ":
        raise PEFormatError("missing MZ signature")
    pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
    if not 64 <= pe_offset <= MAX_PE_OFFSET:
        raise PEFormatError("invalid PE header offset")
    coff = _slice(raw, pe_offset, 24, "PE/COFF header")
    if coff[:4] != b"PE\0\0":
        raise PEFormatError("missing PE signature")
    machine, count, timestamp, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", coff, 4)
    if not 1 <= count <= MAX_SECTIONS:
        raise PEFormatError("invalid section count")
    if not 72 <= opt_size <= 4096:
        raise PEFormatError("invalid optional-header size")
    optional_offset = pe_offset + 24
    optional = _slice(raw, optional_offset, opt_size, "optional header")
    magic = struct.unpack_from("<H", optional, 0)[0]
    if magic == 0x10B:
        image_base = struct.unpack_from("<I", optional, 28)[0]
        bits = 32
    elif magic == 0x20B:
        image_base = struct.unpack_from("<Q", optional, 24)[0]
        bits = 64
    else:
        raise PEFormatError("unsupported optional-header magic")
    image_size = struct.unpack_from("<I", optional, 56)[0]
    size_of_headers = struct.unpack_from("<I", optional, 60)[0]
    subsystem = struct.unpack_from("<H", optional, 68)[0]
    section_table = optional_offset + opt_size
    sections = []
    for index in range(count):
        entry = _slice(raw, section_table + index * 40, 40, "section table")
        name = entry[:8].split(b"\0", 1)[0].decode("ascii", "replace")
        (virtual_size, virtual_address, raw_size, raw_offset, _, _, _, _,
         characteristics) = struct.unpack_from("<IIIIIIHHI", entry, 8)
        sections.append({
            "name": name,
            "virtual_size": virtual_size,
            "virtual_address": virtual_address,
            "raw_size": raw_size,
            "raw_offset": raw_offset,
            "characteristics": characteristics,
            "read": bool(characteristics & 0x40000000),
            "write": bool(characteristics & 0x80000000),
            "execute": bool(characteristics & 0x20000000),
        })

    imports = _parse_imports(raw, bits, optional, sections, size_of_headers)
    exports = _parse_exports(raw, bits, optional, sections, size_of_headers)
    h = hashlib.sha256(raw).hexdigest()
    return {
        "file": path.name,
        "sha256": h,
        "size_bytes": len(raw),
        "machine": _MACHINE.get(machine, f"0x{machine:04x}"),
        "pe_bits": bits,
        "image_base": f"0x{image_base:x}",
        "image_size": image_size,
        "size_of_headers": size_of_headers,
        "coff_timestamp": timestamp,
        "subsystem": subsystem,
        "sections": [section["name"] for section in sections],
        "section_details": sections,
        "imports": imports,
        "exports": exports,
        "export_symbol_count": len(exports),
        "import_dll_count": len(imports),
        "import_symbol_count": sum(item["count"] for item in imports),
        "graphics_profile": _graphics_profile(imports),
        "warcraft_version": None,
        "version_note": "Hash match against a separately verified release catalog is required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+", help="local PE executables or DLLs")
    parser.add_argument("--output", type=Path, help="local report path (never upload game files)")
    args = parser.parse_args()
    results = []
    failed = False
    for path in args.files:
        try:
            results.append(inspect_pe(path))
        except (PEFormatError, OSError) as exc:
            results.append({"file": path.name, "error": str(exc)})
            failed = True
    report = json.dumps({"schema": 2, "results": results}, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
