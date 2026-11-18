#!/usr/bin/env python3
"""Sanitized compatibility census for an already-extracted Warcraft III map.

The tool never decides that a map is compatible. It records evidence useful for
choosing/testing a Classic runtime: JASS/Lua, selected script-native families,
the advisory W3I header, and embedded native-code files.

Use the private wrapper to extract a user-owned/community map with StormLib
without committing or uploading its contents.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

SCRIPT_NAMES = ("war3map.j", "war3map.lua")
NATIVE_SUFFIXES = {".dll", ".exe", ".asi", ".mix", ".m3d", ".flt", ".ax"}
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
INTEROP_MARKERS = {
    "blz_natives": re.compile(r"\bBlz[A-Za-z0-9_]*\s*\("),
    "preload": re.compile(r"\bPreload(?:End|GenClear|GenEnd|GenStart|Refresh)?\s*\("),
    "execute_func": re.compile(r"\bExecuteFunc\s*\("),
    "trigger_execute": re.compile(r"\bTriggerExecute(?:Wait)?\s*\("),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_read_text(path: Path, max_bytes: int = 16 * 1024 * 1024) -> str:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError(f"script too large: {path.name}")
    # JASS maps are commonly Windows-1252; UTF-8 is also common in modern maps.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _w3i_header(path: Path) -> dict | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if len(raw) < 12:
        return {"valid_header": False, "size_bytes": len(raw)}
    file_format, save_count, editor_version = struct.unpack_from("<III", raw, 0)
    # Keep the range deliberately broad. This is advisory metadata only.
    plausible = 1 <= file_format <= 100 and editor_version < 100_000_000
    return {
        "valid_header": plausible,
        "file_format_version": file_format,
        "save_count": save_count,
        "editor_version": editor_version,
        "size_bytes": len(raw),
        "trust": "advisory_only",
    }


def analyze_extracted_map(root: Path, archive_sha256: str | None = None) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")

    files = [p for p in sorted(root.rglob("*")) if p.is_file()]
    relative = [p.relative_to(root).as_posix() for p in files]
    by_lower = {name.lower(): root / name for name in relative}

    scripts = []
    script_texts: list[tuple[str, str]] = []
    for name in SCRIPT_NAMES:
        path = by_lower.get(name)
        if path and path.is_file():
            text = _safe_read_text(path)
            scripts.append({
                "name": name,
                "language": "lua" if name.endswith(".lua") else "jass",
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
            script_texts.append((name, text))

    native_files = []
    suffix_counts: Counter[str] = Counter()
    for rel, path in zip(relative, files):
        suffix = path.suffix.lower()
        if suffix in NATIVE_SUFFIXES:
            native_files.append(rel)
            suffix_counts[suffix] += 1

    marker_counts = Counter()
    blz_names: set[str] = set()
    suspicious_loader_names: set[str] = set()
    for _, text in script_texts:
        for name, rx in INTEROP_MARKERS.items():
            marker_counts[name] += len(rx.findall(text))
        for call in CALL_RE.findall(text):
            if call.startswith("Blz"):
                blz_names.add(call)
            lowered = call.lower()
            if any(token in lowered for token in ("loadlibrary", "getprocaddress", "dll", "plugin")):
                suspicious_loader_names.add(call)

    has_jass = any(item["language"] == "jass" for item in scripts)
    has_lua = any(item["language"] == "lua" for item in scripts)
    if has_lua:
        engine_hint = "classic_1_31_or_newer_feature_set"
    elif has_jass:
        engine_hint = "classic_jass_version_requires_native_census"
    else:
        engine_hint = "script_not_observed"

    w3i_path = by_lower.get("war3map.w3i")
    report = {
        "schema": 1,
        "privacy": "absolute paths and script contents are omitted",
        "archive_sha256": archive_sha256,
        "file_count": len(files),
        "scripts": scripts,
        "script_profile": {
            "has_jass": has_jass,
            "has_lua": has_lua,
            "engine_hint": engine_hint,
            "markers": dict(sorted(marker_counts.items())),
            "blz_native_names": sorted(blz_names),
            "loader_like_call_names": sorted(suspicious_loader_names),
        },
        "w3i_header": _w3i_header(w3i_path) if w3i_path else None,
        "embedded_native_code": {
            "present": bool(native_files),
            "count": len(native_files),
            "suffix_counts": dict(sorted(suffix_counts.items())),
            # Kept in a private report for debugging; no file bytes are emitted.
            "relative_files": native_files,
            "note": (
                "Embedded native code is a compatibility warning, not proof that "
                "the map executes a plugin."
            ),
        },
        "known_core_files": sorted(
            name for name in relative
            if Path(name).name.lower().startswith("war3map")
        ),
        "compatibility": {
            "status": "unverified",
            "requires_runtime_test": True,
            "note": (
                "A script/header census cannot prove map compatibility or multiplayer "
                "determinism. Test the original map unchanged on the selected engine."
            ),
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = analyze_extracted_map(args.extracted, args.archive_sha256)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
