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
    handles = runtime / "handles.c"
    kernel32 = runtime / "kernel32.c"
    required = (system, window, handles, kernel32)
    if not all(path.is_file() for path in required):
        raise PatchError("pinned runtime is missing a required source file")

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

    replace_once(
        handles,
        """#include <mach/mach_time.h>
""",
        """""",
    )
    replace_once(
        handles,
        """static pthread_mutex_t hmu = PTHREAD_MUTEX_INITIALIZER;
""",
        """static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static pthread_mutex_t hmu = PTHREAD_MUTEX_INITIALIZER;
""",
    )
    replace_once(
        handles,
        """            uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
""",
        """            uint64_t now = monotonic_ns();
""",
    )

    replace_once(
        kernel32,
        """#include <mach/mach_time.h>
#include <malloc/malloc.h>
""",
        """#include <malloc_np.h>
""",
    )
    replace_once(
        kernel32,
        """// ---------------- time ----------------
static uint64_t filetime_now(void) {
""",
        """// ---------------- time ----------------
static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint64_t filetime_now(void) {
""",
    )
    replace_once(
        kernel32,
        """void I_kernel32_dll_QueryPerformanceCounter(CPU *c) { wr64(A0, clock_gettime_nsec_np(CLOCK_UPTIME_RAW)); RET(1); }
void I_kernel32_dll_GetTickCount(CPU *c) { RET((uint32_t)(clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1000000)); }
void I_kernel32_dll_GetTickCount64(CPU *c) { RET(clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1000000); }
""",
        """void I_kernel32_dll_QueryPerformanceCounter(CPU *c) { wr64(A0, monotonic_ns()); RET(1); }
void I_kernel32_dll_GetTickCount(CPU *c) { RET((uint32_t)(monotonic_ns() / 1000000)); }
void I_kernel32_dll_GetTickCount64(CPU *c) { RET(monotonic_ns() / 1000000); }
""",
    )
    replace_once(
        kernel32,
        """    uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
""",
        """    uint64_t now = monotonic_ns();
""",
    )
    for old in (
        "malloc_size(p)",
        "malloc_size(h)",
        "malloc_size(PTR(A2))",
    ):
        text = kernel32.read_text(encoding="utf-8")
        if old not in text:
            raise PatchError(f"kernel32.c: missing expected {old}")
        kernel32.write_text(
            text.replace(old, old.replace("malloc_size", "malloc_usable_size")),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    try:
        patch_runtime(args.runtime)
    except (OSError, PatchError) as exc:
        parser.error(str(exc))
    print("PS5 Win64 runtime portability edits applied: system.c window.c handles.c kernel32.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
