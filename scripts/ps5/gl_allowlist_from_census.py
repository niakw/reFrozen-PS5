#!/usr/bin/env python3
"""Derive the exact static OpenGL thunk allowlist from a private PE census.

Input is JSON from scan_install.py or pe_probe.py. Output contains only API
names and relative module basenames; no absolute install path or game bytes.
Dynamic wglGetProcAddress requests are intentionally not guessed here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

GL_NAME_RE = re.compile(r"^gl[A-Za-z0-9_]+$")


class CensusError(ValueError):
    pass


def _results(census: dict) -> list[dict]:
    results = census.get("results")
    if not isinstance(results, list):
        raise CensusError("census has no results array")
    return results


def derive_static_gl_surface(census: dict) -> dict:
    by_api: dict[str, set[str]] = defaultdict(set)
    ordinal_imports: list[dict] = []
    modules_with_opengl: set[str] = set()

    for result in _results(census):
        if not isinstance(result, dict) or "error" in result:
            continue
        module = (
            result.get("relative_file")
            or result.get("file")
            or "<unnamed-module>"
        )
        module = Path(str(module)).name
        imports = result.get("imports", [])
        if not isinstance(imports, list):
            raise CensusError(f"{module}: imports is not an array")
        for library in imports:
            if not isinstance(library, dict):
                raise CensusError(f"{module}: malformed import library entry")
            dll = str(
                library.get("dll_normalized")
                or library.get("dll")
                or ""
            ).lower()
            if dll != "opengl32.dll":
                continue
            modules_with_opengl.add(module)
            symbols = library.get("symbols", [])
            if not isinstance(symbols, list):
                raise CensusError(f"{module}: OpenGL symbols is not an array")
            for raw in symbols:
                symbol = str(raw)
                if symbol.startswith("#"):
                    ordinal_imports.append({"module": module, "symbol": symbol})
                    continue
                if symbol.startswith("wgl"):
                    # WGL is handled by wgl_guest_runtime_ps5.cpp, not the GL
                    # function thunk generator.
                    continue
                if not GL_NAME_RE.fullmatch(symbol):
                    raise CensusError(
                        f"{module}: unexpected opengl32 import name {symbol!r}"
                    )
                by_api[symbol].add(module)

    apis = sorted(by_api)
    return {
        "schema": 1,
        "static_gl_functions": apis,
        "function_count": len(apis),
        "modules_with_opengl": sorted(modules_with_opengl),
        "provenance": {
            name: sorted(by_api[name]) for name in apis
        },
        "ordinal_imports": sorted(
            ordinal_imports,
            key=lambda item: (item["module"], item["symbol"]),
        ),
        "dynamic_proc_surface": "not_observed",
        "note": (
            "This is static-import evidence only. Runtime wglGetProcAddress "
            "requests must be captured separately before final thunk closure."
        ),
    }


def render_allowlist(report: dict) -> str:
    header = [
        "# Generated from local PE census; static opengl32.dll gl* imports only.",
        "# Dynamic wglGetProcAddress requests are NOT included.",
    ]
    return "\n".join(header + report["static_gl_functions"]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        census = json.loads(args.census.read_text(encoding="utf-8"))
        report = derive_static_gl_surface(census)
    except (OSError, json.JSONDecodeError, CensusError) as exc:
        print(f"GL census derivation failed: {exc}", file=sys.stderr)
        return 1

    args.allowlist.parent.mkdir(parents=True, exist_ok=True)
    args.allowlist.write_text(render_allowlist(report), encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"static OpenGL functions: {report['function_count']}; "
        f"modules: {len(report['modules_with_opengl'])}; "
        f"ordinal imports: {len(report['ordinal_imports'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
