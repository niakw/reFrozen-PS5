#!/usr/bin/env python3
"""Apply small, fail-closed PS5 portability edits to the pinned Win64 runtime.

This script deliberately uses exact source substitutions instead of a fuzzy
patch so an upstream change cannot silently alter the porting contract.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"{path.name}: expected exact source fragment once, found {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_runtime(runtime: Path) -> None:
    runtime = runtime.resolve()
    if not runtime.is_dir():
        raise PatchError("runtime root is not a directory")

    system = runtime / "system.c"
    window = runtime / "window.c"
    if not system.is_file() or not window.is_file():
        raise PatchError("pinned runtime is missing system.c/window.c")

    replace_once(
        system,
        """// ---------------- winmm ----------------
static uint64_t ms_now(void) { return clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1000000; }
""",
        """static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

// ---------------- winmm ----------------
static uint64_t ms_now(void) { return monotonic_ns() / 1000000; }
""",
    )
    replace_once(
        system,
        """void I_kernel32_dll_QueryUnbiasedInterruptTime(CPU *c) { wr64(A0, clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 100); RET(1); }
""",
        """void I_kernel32_dll_QueryUnbiasedInterruptTime(CPU *c) { wr64(A0, monotonic_ns() / 100); RET(1); }
""",
    )
    replace_once(
        window,
        """static uint32_t now_ms(void) { return (uint32_t)(clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1000000); }
""",
        """static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint32_t now_ms(void) { return (uint32_t)(monotonic_ns() / 1000000); }
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    try:
        patch_runtime(args.runtime)
    except (OSError, PatchError) as exc:
        parser.error(str(exc))
    print("PS5 Win64 runtime portability edits applied: system.c window.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
