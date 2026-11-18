#!/usr/bin/env python3
"""Generate NightSight RtGame configuration from a READY private build plan.

The generated C source is private build material: it records the exact planned
entry executable name but no local paths or game bytes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class GameConfigError(ValueError):
    pass


def _cstr(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_game_config(plan: dict) -> str:
    if plan.get("status") != "ready_for_private_lift_and_link":
        raise GameConfigError("plan is not ready_for_private_lift_and_link")
    entry = plan.get("entry")
    if not isinstance(entry, dict):
        raise GameConfigError("plan entry metadata is missing")
    exe = entry.get("file")
    sha = str(entry.get("sha256") or "")
    if not isinstance(exe, str) or not exe or not exe.lower().endswith(".exe"):
        raise GameConfigError("planned entry executable is invalid")
    if len(sha) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        raise GameConfigError("planned entry SHA-256 is invalid")

    stem = exe[:-4]
    return f"""// Generated from sanitized reFrozen PS5 private build plan.
// Entry SHA-256: {sha.lower()}
// Do not commit generated private build material.
#include "game.h"

const RtGame rt_game = {{
    .name = "Warcraft III Classic",
    .exe = {_cstr(exe)},
    .win_dir = "C:\\\\Games\\\\Warcraft III",
    .data_name = "refrozen-ps5",
    .log_name = "refrozen-ps5",
    .env_prefix = "REFROZEN",
    .steam_folder = NULL,
    .steam_app_id = 0,
    .relaunch_prefix = {_cstr(stem)},
    .extra_args = NULL,
    .cloud_save_dir = NULL,
    .cloud_prefix = NULL,
    .computer_name = "PS5",
    .pick_folder_msg = NULL,
    .image = NULL,
    .gl_extensions = NULL,
}};
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "private" / "warcraft-win64-lift" / "game.c",
    )
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        source = render_game_config(plan)
    except (OSError, json.JSONDecodeError, GameConfigError) as exc:
        parser.error(str(exc))

    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    try:
        out.relative_to((root / "private").resolve())
    except ValueError:
        parser.error("output must remain under repository /private")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")
    print(out.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
