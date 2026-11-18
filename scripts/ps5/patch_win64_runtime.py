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
    kernel32 = runtime / "kernel32.c"
    if not all(path.is_file() for path in (system, window, kernel32)):
        raise PatchError("pinned runtime is missing system.c/window.c/kernel32.c")

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
        kernel32,
        """#include <mach/mach_time.h>
#include <malloc/malloc.h>
""",
        """#include <malloc_np.h>
#include <sys/umtx.h>
""",
    )
    replace_once(
        kernel32,
        """#include <pthread.h>
""",
        """#include <pthread.h>
#include <pthread_np.h>
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
    replace_once(
        kernel32,
        """#include <os/os_sync_wait_on_address.h>
""",
        """""",
    )
    replace_once(
        kernel32,
        """        __builtin_arm_yield();
""",
        """        __builtin_ia32_pause();
""",
    )
    replace_once(
        kernel32,
        """        os_sync_wait_on_address(w, 2, 4, OS_SYNC_WAIT_ON_ADDRESS_NONE);
""",
        """        (void)_umtx_op((void *)w, UMTX_OP_WAIT_UINT_PRIVATE, 2, NULL, NULL);
""",
    )
    replace_once(
        kernel32,
        """        os_sync_wake_by_address_any((void *)P32(cs + 8), 4, OS_SYNC_WAKE_BY_ADDRESS_NONE);
""",
        """        (void)_umtx_op((void *)P32(cs + 8), UMTX_OP_WAKE_PRIVATE, 1, NULL, NULL);
""",
    )
    for old, expected in (
        ("malloc_size(p)", 1),
        ("malloc_size(h)", 2),
        ("malloc_size(PTR(A2))", 1),
    ):
        text = kernel32.read_text(encoding="utf-8")
        count = text.count(old)
        if count != expected:
            raise PatchError(
                f"kernel32.c: expected {old} {expected} time(s), found {count}"
            )
        kernel32.write_text(
            text.replace(old, old.replace("malloc_size", "malloc_usable_size")),
            encoding="utf-8",
        )

    replace_once(
        kernel32,
        """            if (name && (tid == 0xFFFFFFFFu || tid == rt_thread_id())) pthread_setname_np(name);
""",
        """            if (name && (tid == 0xFFFFFFFFu || tid == rt_thread_id())) pthread_set_name_np(pthread_self(), name);
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
    print("PS5 Win64 runtime portability edits applied: system.c window.c kernel32.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
