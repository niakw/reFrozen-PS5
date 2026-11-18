#!/usr/bin/env python3
"""Scan one local Warcraft install tree for PE modules without executing them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.ps5.pe_probe import inspect_pe, PEFormatError

DEFAULT_SUFFIXES = {".exe", ".dll", ".asi", ".m3d", ".flt", ".ax"}


def scan_install(root: Path, suffixes: set[str] | None = None) -> dict:
    root = root.resolve()
    suffixes = {s.lower() for s in (suffixes or DEFAULT_SUFFIXES)}
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    results = []
    skipped = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            item = inspect_pe(path)
            item["relative_file"] = rel
            results.append(item)
        except (PEFormatError, OSError) as exc:
            # A codec/plugin extension may contain a non-PE payload. Keep only
            # the relative path, never the user's absolute installation path.
            skipped.append({"relative_file": rel, "reason": str(exc)})
    return {
        "schema": 1,
        "root": None,
        "privacy_note": "absolute installation path intentionally omitted",
        "module_count": len(results),
        "skipped_candidate_count": len(skipped),
        "results": results,
        "skipped_candidates": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = scan_install(args.install)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PE modules: {report['module_count']}; skipped candidates: "
          f"{report['skipped_candidate_count']}; report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
