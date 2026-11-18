#!/usr/bin/env python3
"""Map unresolved PS5 runtime symbols back to their source translation units.

Input is the text-only object-results.tsv + object directory produced by
compile-win32-runtime-closure.sh. No game code or proprietary input is read.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import re
import subprocess

SDL_AUDIO = ("Audio",)
SDL_GAMEPAD = ("Gamepad", "Rumble")
SDL_WINDOW = ("Window", "Display", "Cursor", "Fullscreen", "MessageBox")
SDL_RENDER = ("Renderer", "Render", "Surface", "Texture", "SaveBMP")
SDL_EVENT = ("Event", "Key", "Scancode", "Mouse")
SDL_CORE = ("Init", "Quit", "Ticks", "Hint", "Error", "free")


def classify(symbol: str) -> str:
    if symbol.startswith("SDL_"):
        tail = symbol[4:]
        if any(x in tail for x in SDL_AUDIO):
            return "sdl_audio"
        if any(x in tail for x in SDL_GAMEPAD):
            return "sdl_gamepad"
        if any(x in tail for x in SDL_WINDOW):
            return "sdl_window_display"
        if any(x in tail for x in SDL_RENDER):
            return "sdl_renderer_surface"
        if any(x in tail for x in SDL_EVENT):
            return "sdl_event_input"
        if any(x in tail for x in SDL_CORE):
            return "sdl_core_timing"
        return "sdl_other"
    if symbol.startswith("_ZN6recomp") or symbol.startswith("_ZNK6recomp"):
        return "recomp_internal"
    if symbol.startswith(("_ZNSt", "_ZNKSt", "_ZTV", "_ZTI", "_ZTT", "_ZSt",
                          "_Zn", "_Zd", "__cxa_", "__gxx_", "_Unwind_")):
        return "cxx_runtime"
    if symbol.startswith(("gl", "egl")):
        return "graphics_api"
    if symbol.startswith(("sce", "Sce")):
        return "ps5_native"
    if re.match(r"^(accept|bind|connect|recv|send|socket|getaddrinfo|freeaddrinfo|"
                r"inet_|__inet_|setsockopt|getsockopt|listen|shutdown)$", symbol):
        return "network_posix"
    return "libc_posix_or_other"


def parse_nm(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if "U" not in parts:
            continue
        symbol = parts[-1]
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def safe_object_name(relative: str) -> str:
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError(f"unsafe relative source path: {relative}")
    return relative.replace("/", "_") + ".o"


def build_map(results_tsv: Path, object_dir: Path, nm: str) -> dict:
    rows = list(csv.DictReader(results_tsv.open(encoding="utf-8"), delimiter="\t"))
    mappings = []
    by_category = Counter()
    by_file = defaultdict(Counter)
    for row in rows:
        if row.get("status") != "PASS":
            continue
        relative = row["file"]
        obj = object_dir / safe_object_name(relative)
        if not obj.is_file():
            raise FileNotFoundError(f"missing object for PASS unit: {relative}")
        proc = subprocess.run([nm, "--undefined-only", str(obj)],
                              text=True, capture_output=True, check=True)
        for symbol in parse_nm(proc.stdout):
            category = classify(symbol)
            mappings.append({"file": relative, "category": category, "symbol": symbol})
            by_category[category] += 1
            by_file[relative][category] += 1
    unique_symbols = sorted({m["symbol"] for m in mappings})
    sdl_symbols = sorted(s for s in unique_symbols if s.startswith("SDL_"))
    return {
        "schema": 1,
        "objects": sum(1 for r in rows if r.get("status") == "PASS"),
        "mapping_rows": len(mappings),
        "unique_symbols": len(unique_symbols),
        "unique_sdl_symbols": len(sdl_symbols),
        "sdl_symbols": sdl_symbols,
        "category_reference_rows": dict(sorted(by_category.items())),
        "files": {
            file: dict(sorted(counts.items()))
            for file, counts in sorted(by_file.items())
        },
        "mappings": sorted(mappings, key=lambda x: (x["file"], x["category"], x["symbol"])),
        "note": "Counts are unresolved symbol references per object, not missing implementations.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_tsv", type=Path)
    p.add_argument("object_dir", type=Path)
    p.add_argument("--nm", default="llvm-nm-18")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = build_map(args.results_tsv, args.object_dir, args.nm)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"REFROZEN_PS5_HOST_IMPORT_MAP pass=1 objects={report['objects']} "
        f"unique_symbols={report['unique_symbols']} "
        f"unique_sdl={report['unique_sdl_symbols']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
