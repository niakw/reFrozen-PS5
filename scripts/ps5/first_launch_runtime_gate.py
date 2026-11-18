#!/usr/bin/env python3
"""Fail-closed first-launch runtime gate for a private Warcraft PE census.

This does not infer game behavior. It combines:
  1. a sanitized runtime gap report,
  2. the PS5 compile census (results.tsv),
  3. explicit renderer/audio capability markers,
to say whether every *observed* first-launch dependency has a compiled PS5
runtime route.

A PASS is still not device qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Normalized imported DLL -> runtime translation units or external PS5 route.
_DLL_REQUIREMENTS = {
    "kernel32.dll": {"kernel32.c", "system.c", "handles.c", "files.c"},
    "kernelbase.dll": {"kernel32.c", "system.c", "handles.c", "files.c"},
    "ntdll.dll": {"kernel32.c"},
    "advapi32.dll": {"system.c"},
    "user32.dll": {"user32.c", "window.c", "display.c"},
    "gdi32.dll": {"user32.c", "display.c"},
    "imm32.dll": {"input.c"},
    "dinput.dll": {"dinput.c"},
    "dinput8.dll": {"dinput.c"},
    "xinput1_1.dll": {"input.c"},
    "xinput1_2.dll": {"input.c"},
    "xinput1_3.dll": {"input.c"},
    "xinput1_4.dll": {"input.c"},
    "xinput9_1_0.dll": {"input.c"},
    "wsock32.dll": {"sockets.c"},
    "ws2_32.dll": {"sockets.c"},
    "mswsock.dll": {"sockets.c"},
    "winmm.dll": {"system.c"},
    "ole32.dll": {"input.c", "wasapi.c", "xaudio2.c"},
    "opengl32.dll": {"@wgl_egl"},
    "bcrypt.dll": {"bcrypt.c"},
}

_MARKER_REQUIREMENTS = {
    "wasapi_mmdevice_enumerator": {"wasapi.c"},
    "xaudio2_27": {"xaudio2.c"},
    "xaudio2_27_debug": {"xaudio2.c"},
    "iid_ixaudio2_27": {"xaudio2.c"},
}


def parse_compile_census(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[1] not in {"PASS", "FAIL"}:
            raise ValueError(f"invalid compile-census row: {raw!r}")
        if parts[0] in out:
            raise ValueError(f"duplicate compile-census unit: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


def build_gate(gap_report: dict, compile_status: dict[str, str],
               external_routes: set[str]) -> dict:
    required: set[str] = set()
    reasons: dict[str, set[str]] = {}
    unresolved_imports: list[dict] = []
    unknown_dlls: set[str] = set()

    def need(item: str, reason: str) -> None:
        required.add(item)
        reasons.setdefault(item, set()).add(reason)

    for module in gap_report.get("modules", []):
        filename = module.get("file", "<unknown>")
        for lib in module.get("imports", []):
            dll = str(lib.get("dll", "")).lower()
            if dll in _DLL_REQUIREMENTS:
                for item in _DLL_REQUIREMENTS[dll]:
                    need(item, f"{filename}: import {dll}")
            elif dll and lib.get("symbols"):
                unknown_dlls.add(dll)

            for symbol in lib.get("symbols", []):
                status = symbol.get("reference_status")
                if status in {
                    "unmapped", "reference_other_arch",
                    "local_module_export_missing", "ordinal_needs_manual",
                }:
                    unresolved_imports.append({
                        "file": filename,
                        "dll": dll,
                        "symbol": symbol.get("name"),
                        "status": status,
                    })

        for marker in module.get("capability_markers", []):
            name = marker.get("name")
            for item in _MARKER_REQUIREMENTS.get(name, ()):
                need(item, f"{filename}: marker {name}")

    missing_compile = []
    for item in sorted(required):
        if item.startswith("@"):
            if item[1:] not in external_routes:
                missing_compile.append({
                    "requirement": item,
                    "status": "external_route_unproven",
                    "reasons": sorted(reasons[item]),
                })
            continue
        status = compile_status.get(item)
        if status != "PASS":
            missing_compile.append({
                "requirement": item,
                "status": status or "not_in_compile_census",
                "reasons": sorted(reasons[item]),
            })

    # Unknown DLLs are recorded for triage but do not automatically fail here:
    # runtime_gap_report's per-symbol reference status is the stronger gate.
    passed = not missing_compile and not unresolved_imports
    return {
        "schema": 1,
        "passed": passed,
        "meaning": (
            "PASS means every observed mapped first-launch route compiles for the "
            "PS5 ABI and no imported symbol is unresolved. It is not proof of "
            "runtime behavior, renderer correctness, audio correctness or device boot."
        ),
        "required": [
            {"requirement": item, "reasons": sorted(reasons[item])}
            for item in sorted(required)
        ],
        "missing_compile_routes": missing_compile,
        "unresolved_imports": unresolved_imports,
        "unknown_dlls_for_triage": sorted(unknown_dlls),
        "external_routes_proven": sorted(external_routes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gap_report", type=Path)
    parser.add_argument("compile_census", type=Path)
    parser.add_argument("--external-route", action="append", default=[],
                        help="proven external route, e.g. wgl_egl")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = json.loads(args.gap_report.read_text(encoding="utf-8"))
    compile_status = parse_compile_census(args.compile_census)
    gate = build_gate(report, compile_status, set(args.external_route))
    payload = json.dumps(gate, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
