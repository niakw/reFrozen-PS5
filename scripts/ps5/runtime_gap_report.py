#!/usr/bin/env python3
"""Compare a local PE census with architecture-appropriate recomp runtimes.

For PE32 modules the reference is reFrozen/x86recomp's Win32 HLE.
For PE32+ modules an optional Win64 runtime source tree can be supplied
(e.g. the pinned NightSight Recomp-Framework runtime).

A source handler match is only triage evidence. It never means the handler is
PS5-portable or device-qualified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

HLE_RE = re.compile(r'HLE\("([^"]+)",\s*([A-Za-z_][A-Za-z0-9_]*),\s*\d+\)')
WIN64_HLE_RE = re.compile(
    r'\bI_([A-Za-z0-9_]+)_dll_([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*CPU\s*\*'
)


def _reference_hle_files(root: Path) -> tuple[list[Path], bool]:
    files = list(sorted((root / "patches" / "x86recomp").glob("*.patch")))
    runtime = root / "tools" / "x86recomp" / "src" / "runtime"
    complete = runtime.is_dir()
    if complete:
        for suffix in ("*.c", "*.cc", "*.cpp", "*.h", "*.hpp"):
            files.extend(sorted(runtime.rglob(suffix)))
    return files, complete


def reference_hle_surface(root: Path) -> set[tuple[str, str]]:
    surface: set[tuple[str, str]] = set()
    files, _ = _reference_hle_files(root)
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for dll, api in HLE_RE.findall(text):
            surface.add((dll.lower(), api))
    return surface


def reference_win64_handlers(
    runtime_root: Path | None,
) -> dict[tuple[str, str], set[str]]:
    """Map explicit Win64 HLE handlers to their implementation translation units.

    Only implementation sources count as evidence. Header declarations are not
    sufficient to prove that an imported API has code behind it. Returned paths
    are relative to the runtime root so private absolute paths never leak.
    """
    if runtime_root is None:
        return {}
    runtime_root = runtime_root.resolve()
    if not runtime_root.is_dir():
        return {}
    handlers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for suffix in ("*.c", "*.cc", "*.cpp", "*.m", "*.mm"):
        for path in sorted(runtime_root.rglob(suffix)):
            text = path.read_text(encoding="utf-8", errors="replace")
            unit = path.relative_to(runtime_root).as_posix()
            for dll, api in WIN64_HLE_RE.findall(text):
                handlers[(dll.lower() + ".dll", api)].add(unit)
    return handlers


def reference_win64_surface(runtime_root: Path | None) -> set[tuple[str, str]]:
    """Compatibility helper: the implemented Win64 HLE API surface."""
    return set(reference_win64_handlers(runtime_root))


def _target_runtime(result: dict) -> str:
    bits = result.get("pe_bits")
    if bits == 64:
        return "win64_candidate"
    if bits == 32:
        return "refrozen_x86"
    return "unknown"


def build_gap_report(
    census: dict, root: Path, win64_runtime_root: Path | None = None
) -> dict:
    known32 = reference_hle_surface(root)
    known64_handlers = reference_win64_handlers(win64_runtime_root)
    known64 = set(known64_handlers)
    _, reference32_complete = _reference_hle_files(root)
    reference64_complete = (
        win64_runtime_root is not None and win64_runtime_root.resolve().is_dir()
    )

    local_modules = {
        result["file"].lower(): result
        for result in census.get("results", [])
        if "error" not in result and result.get("file")
    }
    local_exports = {}
    for filename, result in local_modules.items():
        by_ordinal = {
            item["ordinal"]: item for item in result.get("exports", [])
        }
        by_name = {
            item["name"]: item
            for item in result.get("exports", [])
            if item.get("name")
        }
        local_exports[filename] = (by_ordinal, by_name)

    modules = []
    totals = Counter()
    missing_by_dll: dict[str, list[str]] = defaultdict(list)

    for result in census.get("results", []):
        if "error" in result:
            modules.append({"file": result.get("file"), "error": result["error"]})
            continue

        target_runtime = _target_runtime(result)
        target_surface = known64 if target_runtime == "win64_candidate" else known32
        other_surface = known32 if target_runtime == "win64_candidate" else known64
        imports_out = []

        for library in result.get("imports", []):
            dll = library["dll_normalized"]
            symbols_out = []
            target = local_modules.get(dll)
            ordinal_exports, named_exports = local_exports.get(dll, ({}, {}))

            for symbol in library.get("symbols", []):
                resolved_name = None
                reference_units: list[str] = []
                if symbol.startswith("#"):
                    try:
                        ordinal = int(symbol[1:])
                    except ValueError:
                        ordinal = -1
                    exported = ordinal_exports.get(ordinal)
                    if exported is not None:
                        resolved_name = exported.get("name") or symbol
                        status = "local_module_ordinal"
                    else:
                        status = "ordinal_needs_manual"
                elif target is not None:
                    if not target.get("exports") or symbol in named_exports:
                        status = "local_module"
                    else:
                        status = "local_module_export_missing"
                elif (dll, symbol) in target_surface:
                    status = (
                        "reference_win64_hle"
                        if target_runtime == "win64_candidate"
                        else "reference_hle"
                    )
                    if status == "reference_win64_hle":
                        reference_units = sorted(
                            known64_handlers.get((dll, symbol), ())
                        )
                elif (dll, symbol) in other_surface:
                    # Useful implementation evidence, but the ABI/runtime model differs.
                    status = "reference_other_arch"
                    missing_by_dll[dll].append(symbol)
                else:
                    status = "unmapped"
                    missing_by_dll[dll].append(symbol)

                totals[status] += 1
                symbols_out.append({
                    "name": symbol,
                    "resolved_name": resolved_name,
                    "reference_status": status,
                    "reference_units": reference_units,
                    "ps5_status": "unverified",
                })

            imports_out.append({
                "dll": library["dll"],
                "runtime_area": library.get("runtime_area", "unknown"),
                "symbols": symbols_out,
            })

        modules.append({
            "file": result["file"],
            "sha256": result.get("sha256"),
            "machine": result.get("machine"),
            "pe_bits": result.get("pe_bits"),
            "version_resource": result.get("version_resource"),
            "target_runtime": target_runtime,
            "imports": imports_out,
            "capability_markers": result.get("com_guid_markers", []),
        })

    return {
        "schema": 4,
        "meaning": {
            "reference_hle": (
                "handler exists in reFrozen/x86recomp Win32 HLE for a PE32 target; "
                "PS5 portability not proven"
            ),
            "reference_win64_hle": (
                "handler exists in the supplied Win64 runtime implementation source for "
                "a PE32+ target; reference_units names the source translation unit(s), "
                "whose PS5 compilation must be proven separately"
            ),
            "reference_other_arch": (
                "handler exists only in the other architecture runtime; useful as a "
                "porting reference but not target-runtime coverage"
            ),
            "local_module": (
                "matching locally scanned DLL is present and the named export is not contradicted"
            ),
            "local_module_ordinal": (
                "ordinal resolved against the matching locally scanned DLL export table"
            ),
            "local_module_export_missing": (
                "matching local DLL was scanned but its export table lacks the named import"
            ),
            "ordinal_needs_manual": (
                "ordinal import cannot be matched without exact DLL export/version evidence"
            ),
            "unmapped": "no matching local module or target/other runtime handler found",
            "ps5_status": "always unverified until compiled and exercised on PS5",
        },
        # Backwards-compatible Win32 fields used by earlier reports.
        "reference_hle_count": len(known32),
        "reference_surface": {
            "mode": (
                "full_local_x86recomp_checkout_plus_patches"
                if reference32_complete else "patch_delta_only"
            ),
            "complete": reference32_complete,
            "note": (
                "tools/x86recomp is present; handlers scanned from patched runtime checkout"
                if reference32_complete
                else "tools/x86recomp absent; only reFrozen patch additions/changes are visible"
            ),
        },
        "reference_surfaces": {
            "win32_refrozen": {
                "handler_count": len(known32),
                "complete": reference32_complete,
            },
            "win64_candidate": {
                "handler_count": len(known64),
                "complete": reference64_complete,
                "root_recorded": None,  # never disclose the user's absolute local path
            },
        },
        "summary": dict(sorted(totals.items())),
        "missing_by_dll": {
            dll: sorted(set(names))
            for dll, names in sorted(missing_by_dll.items())
        },
        "modules": modules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path, help="JSON produced by scan_install.py/pe_probe.py")
    parser.add_argument(
        "--root", type=Path,
        default=Path(__file__).resolve().parents[2],
        help="refrozen_ps5 repository root",
    )
    parser.add_argument(
        "--win64-runtime-root", type=Path,
        help="optional local Win64 recomp runtime source tree (path omitted from output)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    census = json.loads(args.census.read_text(encoding="utf-8"))
    report = build_gap_report(
        census, args.root.resolve(),
        args.win64_runtime_root.resolve() if args.win64_runtime_root else None,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
