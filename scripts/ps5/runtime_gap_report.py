#!/usr/bin/env python3
"""Compare a local PE census with reFrozen's existing Win32 HLE reference surface.

"reference_hle" means an API has a handler in the current reFrozen/x86recomp
patch set. It does NOT mean the implementation is PS5-portable or validated.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

HLE_RE = re.compile(r'HLE\("([^"]+)",\s*([A-Za-z_][A-Za-z0-9_]*),\s*\d+\)')


def reference_hle_surface(root: Path) -> set[tuple[str, str]]:
    surface: set[tuple[str, str]] = set()
    patch_root = root / "patches" / "x86recomp"
    for path in sorted(patch_root.glob("*.patch")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for dll, api in HLE_RE.findall(text):
            surface.add((dll.lower(), api))
    return surface


def build_gap_report(census: dict, root: Path) -> dict:
    known = reference_hle_surface(root)
    local_modules = {
        result["file"].lower(): result
        for result in census.get("results", [])
        if "error" not in result and result.get("file")
    }
    local_exports = {}
    for filename, result in local_modules.items():
        by_ordinal = {item["ordinal"]: item for item in result.get("exports", [])}
        by_name = {item["name"]: item for item in result.get("exports", []) if item.get("name")}
        local_exports[filename] = (by_ordinal, by_name)
    modules = []
    totals = Counter()
    missing_by_dll: dict[str, list[str]] = defaultdict(list)
    for result in census.get("results", []):
        if "error" in result:
            modules.append({"file": result.get("file"), "error": result["error"]})
            continue
        imports_out = []
        for library in result.get("imports", []):
            dll = library["dll_normalized"]
            symbols_out = []
            target = local_modules.get(dll)
            ordinal_exports, named_exports = local_exports.get(dll, ({}, {}))
            for symbol in library.get("symbols", []):
                resolved_name = None
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
                elif (dll, symbol) in known:
                    status = "reference_hle"
                else:
                    status = "unmapped"
                    missing_by_dll[dll].append(symbol)
                totals[status] += 1
                symbols_out.append({"name": symbol, "resolved_name": resolved_name,
                                    "reference_status": status,
                                    "ps5_status": "unverified"})
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
            "imports": imports_out,
        })
    return {
        "schema": 1,
        "meaning": {
            "reference_hle": "handler exists in current reFrozen x86recomp patches; PS5 portability not proven",
            "local_module": "matching locally scanned DLL is present and the named export is not contradicted",
            "local_module_ordinal": "ordinal resolved against the matching locally scanned DLL export table",
            "local_module_export_missing": "matching local DLL was scanned but its export table does not contain the named import",
            "ordinal_needs_manual": "ordinal import cannot be matched without the exact DLL export/version evidence",
            "unmapped": "no matching local module or exact HLE handler found in current reFrozen patch set",
            "ps5_status": "always unverified until compiled and exercised on the PS5 runtime",
        },
        "reference_hle_count": len(known),
        "summary": dict(sorted(totals.items())),
        "missing_by_dll": {dll: sorted(set(names)) for dll, names in sorted(missing_by_dll.items())},
        "modules": modules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path, help="JSON produced by pe_probe.py")
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[2],
                        help="refrozen_ps5 repository root")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    census = json.loads(args.census.read_text(encoding="utf-8"))
    report = build_gap_report(census, args.root.resolve())
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
