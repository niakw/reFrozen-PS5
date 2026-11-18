#!/usr/bin/env python3
"""Read-only PE architecture fingerprinting for user-owned Warcraft III installs.

Only metadata and SHA-256 leave this process. It cannot determine a Warcraft
patch release from the PE timestamp or 'FileVersion' metadata; an independently
verified, version-specific hash catalog is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_PE_OFFSET = 1024 * 1024
MAX_SECTIONS = 96
_MACHINE = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "arm64"}


class PEFormatError(ValueError):
    """Unsupported or malformed portable executable."""


def _read_exact(file, count: int, label: str) -> bytes:
    data = file.read(count)
    if len(data) != count:
        raise PEFormatError(f"truncated {label}")
    return data


def inspect_pe(path: Path) -> dict:
    """Parse COFF and optional headers without loading or executing code."""
    path = Path(path)
    with path.open("rb") as file:
        dos = _read_exact(file, 64, "DOS header")
        if dos[:2] != b"MZ":
            raise PEFormatError("missing MZ signature")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        if not 64 <= pe_offset <= MAX_PE_OFFSET:
            raise PEFormatError("invalid PE header offset")
        file.seek(pe_offset)
        coff = _read_exact(file, 24, "PE/COFF header")
        if coff[:4] != b"PE\0\0":
            raise PEFormatError("missing PE signature")
        machine, count, timestamp, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", coff, 4)
        if not 1 <= count <= MAX_SECTIONS:
            raise PEFormatError("invalid section count")
        if not 72 <= opt_size <= 4096:
            raise PEFormatError("invalid optional-header size")
        optional = _read_exact(file, opt_size, "optional header")
        magic = struct.unpack_from("<H", optional, 0)[0]
        if magic == 0x10B:  # PE32
            image_base = struct.unpack_from("<I", optional, 28)[0]
            bits = 32
        elif magic == 0x20B:  # PE32+
            image_base = struct.unpack_from("<Q", optional, 24)[0]
            bits = 64
        else:
            raise PEFormatError("unsupported optional-header magic")
        image_size = struct.unpack_from("<I", optional, 56)[0]
        subsystem = struct.unpack_from("<H", optional, 68)[0]
        sections = []
        for _ in range(count):
            entry = _read_exact(file, 40, "section table")
            sections.append(entry[:8].split(b"\0", 1)[0].decode("ascii", "replace"))

    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return {
        "file": path.name,
        "sha256": h.hexdigest(),
        "size_bytes": path.stat().st_size,
        "machine": _MACHINE.get(machine, f"0x{machine:04x}"),
        "pe_bits": bits,
        "image_base": f"0x{image_base:x}",
        "image_size": image_size,
        "coff_timestamp": timestamp,
        "subsystem": subsystem,
        "sections": sections,
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
    report = json.dumps({"schema": 1, "results": results}, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
