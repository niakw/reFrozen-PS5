#!/usr/bin/env python3
"""Inventory SDL3 function calls in the patched x86recomp runtime.

The 61-symbol baseline comes from the native PS5 55-object closure. This tool
maps symbols back to source files so native replacements can be implemented by
functional group instead of with permissive stubs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

EXPECTED_UNRESOLVED = {
    "SDL_ClearAudioStream","SDL_CloseGamepad","SDL_CreateRenderer",
    "SDL_CreateSurfaceFrom","SDL_CreateTexture","SDL_CreateWindow",
    "SDL_DestroyAudioStream","SDL_DestroyRenderer","SDL_DestroySurface",
    "SDL_DestroyTexture","SDL_DestroyWindow","SDL_GamepadConnected",
    "SDL_GetAudioStreamQueued","SDL_GetCurrentAudioDriver",
    "SDL_GetDesktopDisplayMode","SDL_GetDisplayForWindow",
    "SDL_GetDisplayUsableBounds","SDL_GetError","SDL_GetFullscreenDisplayModes",
    "SDL_GetGamepadAxis","SDL_GetGamepadButton","SDL_GetGamepadID",
    "SDL_GetGamepads","SDL_GetKeyFromScancode","SDL_GetPrimaryDisplay",
    "SDL_GetScancodeFromName","SDL_GetTicks","SDL_GetTicksNS",
    "SDL_GetWindowFlags","SDL_GetWindowID","SDL_GetWindowSize",
    "SDL_HideCursor","SDL_HideWindow","SDL_Init","SDL_InitSubSystem",
    "SDL_MinimizeWindow","SDL_OpenAudioDeviceStream","SDL_OpenGamepad",
    "SDL_PollEvent","SDL_PutAudioStreamData","SDL_QuitSubSystem",
    "SDL_RaiseWindow","SDL_RenderClear","SDL_RenderPresent","SDL_RenderTexture",
    "SDL_RestoreWindow","SDL_ResumeAudioStreamDevice","SDL_RumbleGamepad",
    "SDL_SaveBMP","SDL_SetHint","SDL_SetWindowFullscreen",
    "SDL_SetWindowFullscreenMode","SDL_SetWindowRelativeMouseMode",
    "SDL_SetWindowSize","SDL_SetWindowTitle","SDL_ShowCursor",
    "SDL_ShowMessageBox","SDL_ShowWindow","SDL_UpdateTexture",
    "SDL_WaitEventTimeout","SDL_free",
}

GROUPS = {
    "core_time": {
        "SDL_Init","SDL_InitSubSystem","SDL_QuitSubSystem","SDL_GetError",
        "SDL_SetHint","SDL_GetTicks","SDL_GetTicksNS","SDL_free",
    },
    "window_display_events": {
        "SDL_CreateWindow","SDL_DestroyWindow","SDL_GetWindowFlags",
        "SDL_GetWindowID","SDL_GetWindowSize","SDL_HideWindow","SDL_ShowWindow",
        "SDL_MinimizeWindow","SDL_RaiseWindow","SDL_RestoreWindow",
        "SDL_SetWindowFullscreen","SDL_SetWindowFullscreenMode",
        "SDL_SetWindowRelativeMouseMode","SDL_SetWindowSize",
        "SDL_SetWindowTitle","SDL_HideCursor","SDL_ShowCursor",
        "SDL_ShowMessageBox","SDL_PollEvent","SDL_WaitEventTimeout",
        "SDL_GetDesktopDisplayMode","SDL_GetDisplayForWindow",
        "SDL_GetDisplayUsableBounds","SDL_GetFullscreenDisplayModes",
        "SDL_GetPrimaryDisplay","SDL_GetKeyFromScancode",
        "SDL_GetScancodeFromName",
    },
    "gamepad": {
        "SDL_GetGamepads","SDL_OpenGamepad","SDL_CloseGamepad",
        "SDL_GamepadConnected","SDL_GetGamepadAxis","SDL_GetGamepadButton",
        "SDL_GetGamepadID","SDL_RumbleGamepad",
    },
    "audio_stream": {
        "SDL_OpenAudioDeviceStream","SDL_DestroyAudioStream",
        "SDL_ClearAudioStream","SDL_GetAudioStreamQueued",
        "SDL_PutAudioStreamData","SDL_ResumeAudioStreamDevice",
        "SDL_GetCurrentAudioDriver",
    },
    "aux_renderer_surface": {
        "SDL_CreateRenderer","SDL_DestroyRenderer","SDL_RenderClear",
        "SDL_RenderPresent","SDL_CreateSurfaceFrom","SDL_DestroySurface",
        "SDL_CreateTexture","SDL_DestroyTexture","SDL_UpdateTexture",
        "SDL_RenderTexture","SDL_SaveBMP",
    },
}
assert set().union(*GROUPS.values()) == EXPECTED_UNRESOLVED
CALL_RE = re.compile(r"\b(SDL_[A-Za-z0-9_]+)\s*\(")


def scan(root: Path) -> dict:
    root = root.resolve()
    by_symbol: dict[str, set[str]] = {}
    by_file: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".cpp", ".cc", ".c", ".hpp", ".h"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        calls = set(CALL_RE.findall(text))
        if not calls:
            continue
        rel = path.relative_to(root).as_posix()
        by_file[rel] = calls
        for symbol in calls:
            by_symbol.setdefault(symbol, set()).add(rel)

    actual = set(by_symbol)
    expected_seen = actual & EXPECTED_UNRESOLVED
    extras = actual - EXPECTED_UNRESOLVED
    missing_from_source = EXPECTED_UNRESOLVED - actual
    categories = {
        name: {
            "symbols": sorted(symbols),
            "seen": sorted(symbols & actual),
            "files": sorted({f for s in symbols for f in by_symbol.get(s, set())}),
        }
        for name, symbols in GROUPS.items()
    }
    return {
        "schema": 1,
        "expected_unresolved_count": len(EXPECTED_UNRESOLVED),
        "runtime_sdl_call_count": len(actual),
        "expected_unresolved_seen_in_source": len(expected_seen),
        "expected_unresolved_missing_from_source": sorted(missing_from_source),
        "additional_sdl_calls_not_in_55_object_unresolved_baseline": sorted(extras),
        "groups": categories,
        "symbol_to_files": {s: sorted(v) for s, v in sorted(by_symbol.items())},
        "file_to_symbols": {f: sorted(v) for f, v in sorted(by_file.items())},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runtime", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = scan(args.runtime)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    print(
        "REFROZEN_PS5_SDL_CONTRACT "
        f"baseline={report['expected_unresolved_count']} "
        f"source_seen={report['expected_unresolved_seen_in_source']} "
        f"runtime_calls={report['runtime_sdl_call_count']} "
        f"extras={len(report['additional_sdl_calls_not_in_55_object_unresolved_baseline'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
