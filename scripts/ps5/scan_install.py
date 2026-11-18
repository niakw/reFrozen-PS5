#!/usr/bin/env python3
"""Scan one local Warcraft install tree for PE modules without executing them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.ps5.pe_probe import inspect_pe, PEFormatError

DEFAULT_SUFFIXES = {".exe", ".dll", ".asi", ".m3d", ".flt", ".ax"}


LEGACY_MPQ_NAMES = (
    "war3.mpq", "war3local.mpq", "war3x.mpq", "war3xlocal.mpq",
    "war3patch.mpq",
)


def _child_ci(parent: Path, name: str) -> Path | None:
    if not parent.is_dir():
        return None
    wanted = name.casefold()
    try:
        for child in parent.iterdir():
            if child.name.casefold() == wanted:
                return child
    except OSError:
        return None
    return None


def detect_storage_layout(root: Path) -> dict:
    """Classify only well-known install-container markers; never enumerate assets."""
    data = _child_ci(root, "Data")
    data_data = _child_ci(data, "data") if data else None
    data_indices = _child_ci(data, "indices") if data else None
    data_config = _child_ci(data, "config") if data else None
    casc = {
        "build_info": bool((root / ".build.info").is_file()),
        "data_dir": bool(data and data.is_dir()),
        "data_data": bool(data_data and data_data.is_dir()),
        "data_indices": bool(data_indices and data_indices.is_dir()),
        "data_config": bool(data_config and data_config.is_dir()),
    }

    root_files = {}
    try:
        root_files = {
            p.name.casefold(): p.name
            for p in root.iterdir()
            if p.is_file()
        }
    except OSError:
        pass
    mpqs = [name for name in LEGACY_MPQ_NAMES if name in root_files]

    casc_strong = casc["data_dir"] and (casc["data_data"] or casc["data_indices"])
    mpq_strong = "war3.mpq" in mpqs and (
        "war3x.mpq" in mpqs or "war3patch.mpq" in mpqs
    )
    if casc_strong and mpq_strong:
        kind = "mixed_casc_and_legacy_mpq"
    elif casc_strong:
        kind = "casc"
    elif mpq_strong:
        kind = "legacy_mpq"
    elif casc["build_info"] or casc["data_dir"] or mpqs:
        kind = "partial_or_unrecognized"
    else:
        kind = "unknown"

    return {
        "classification": kind,
        "casc_markers": casc,
        "legacy_mpq_markers": mpqs,
        "note": (
            "Container markers are structural evidence only. Warcraft III 1.30+ "
            "game data uses CASC; custom .w3m/.w3x maps remain separate map containers."
        ),
    }



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
        "storage_layout": detect_storage_layout(root),
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
