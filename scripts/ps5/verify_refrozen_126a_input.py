#!/usr/bin/env python3
"""Check a private Warcraft III PE census against reFrozen's exact 1.26a input.

Uses only metadata from scan_install.py. Never reads executable bytes, invokes
the game, uploads assets, or emits private absolute paths.
The four SHA-256 values below are publicly documented in upstream
reference/FEASIBILITY.md (native-install / Wine oracle, 1.26a).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REFERENCE = "retronative/refrozen reference/FEASIBILITY.md (1.26a)"
BUILD = "1.26.0.6401"
EXPECTED_CORE_SHA256 = {
    "war3.exe": "28173101fcbeb4cdcac0f83e0e724aa444209b479a2ac1c1784e0d4310889909",
    "game.dll": "6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c",
    "storm.dll": "eecc42b05a91413dee10588a654c6cca05836e7513af6c7c568a56124bf97d0a",
    "mss32.dll": "1f9a83f42de0e7899a7f6772e5cbad6ed10c16cc5f15246c8d80b9f4fe25fc4a",
}
LIFTER_MODULES = (
    "war3.exe", "game.dll", "storm.dll", "mss32.dll", "msvcr80.dll",
    "ijl15.dll", "redist/miles/mp3dec.asi", "redist/miles/mssfast.m3d",
    "redist/miles/msseax2.m3d", "redist/miles/mssdolby.m3d",
    "redist/miles/reverb3.flt",
)
GAME_ASSETS = ("war3.mpq", "war3x.mpq", "war3patch.mpq", "war3xlocal.mpq")
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"


def _module_index(census: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in census.get("results", []):
        if not isinstance(entry, dict) or "error" in entry:
            continue
        relative = entry.get("relative_file") or entry.get("file")
        if not isinstance(relative, str):
            continue
        relative = relative.replace("\\", "/").casefold()
        out.setdefault(relative, []).append(entry)
    return out


def asset_status(install_root: Path | None) -> dict[str, str]:
    if install_root is None:
        return {name: "not_checked" for name in GAME_ASSETS}
    root = Path(install_root)
    if not root.is_dir():
        return {name: "root_unavailable" for name in GAME_ASSETS}
    entries = {p.name.casefold(): p for p in root.iterdir()}
    result = {}
    for name in GAME_ASSETS:
        path = entries.get(name)
        if path is None or not path.is_file() or path.is_symlink():
            result[name] = "missing_or_unsafe"
            continue
        try:
            with path.open("rb") as file:
                prefix = file.read(128)
            if prefix.startswith(LFS_POINTER):
                result[name] = "lfs_pointer_only"
            elif path.stat().st_size < 512:
                result[name] = "too_small"
            else:
                result[name] = "materialized_unverified"
        except OSError:
            result[name] = "unreadable"
    return result


def validate(census: dict, install_root: Path | None = None) -> dict:
    indexed = _module_index(census)
    failures = []
    matched = []
    present = []
    for name in LIFTER_MODULES:
        entries = indexed.get(name, [])
        if len(entries) != 1:
            failures.append({"module": name, "reason": "missing" if not entries else "duplicate"})
            continue
        entry = entries[0]
        present.append(name)
        if entry.get("pe_bits") != 32 or entry.get("machine") != "x86":
            failures.append({"module": name, "reason": "not_pe32_x86"})
            continue
        expected = EXPECTED_CORE_SHA256.get(name)
        if expected:
            if str(entry.get("sha256", "")).lower() != expected:
                failures.append({"module": name, "reason": "sha256_not_matching_upstream_126a"})
            else:
                matched.append(name)
    for name in ("war3.exe", "game.dll"):
        entries = indexed.get(name, [])
        if len(entries) == 1:
            version = (entries[0].get("version_resource") or {}).get("file_version")
            if version != BUILD:
                failures.append({"module": name, "reason": "file_version_not_126a_6401"})
    assets = asset_status(install_root)
    ready_lift = not failures and len(present) == len(LIFTER_MODULES)
    assets_present = all(status == "materialized_unverified" for status in assets.values())
    return {
        "schema": 1,
        "reference": REFERENCE,
        "expected_build": BUILD,
        "modules_present": len(present),
        "modules_required": len(LIFTER_MODULES),
        "core_hashes_matching": sorted(matched),
        "other_modules_sha256_status": "architecture_present_not_exact_hash_verified",
        "failures": failures,
        "asset_status": assets,
        "ready_for_lifter": ready_lift,
        "ready_for_game_launch": bool(ready_lift and assets_present),
        "disclaimer": (
            "A lifter-ready census is not a successful recompilation; asset "
            "materialization is not validation of MPQ contents or launch."
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("census", type=Path, help="local private scan_install JSON")
    p.add_argument("--install", type=Path, help="optional local install directory for MPQ checks")
    p.add_argument("--output", type=Path, help="write sanitized metadata JSON")
    p.add_argument("--require-assets", action="store_true", help="also require materialized MPQs")
    args = p.parse_args()
    report = validate(json.loads(args.census.read_text(encoding="utf-8")), args.install)
    result = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    if not report["ready_for_lifter"]:
        return 2
    if args.require_assets and not report["ready_for_game_launch"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
