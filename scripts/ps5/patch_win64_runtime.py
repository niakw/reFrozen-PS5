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
    files = runtime / "files.c"
    handles = runtime / "handles.c"
    if not all(path.is_file() for path in (system, window, kernel32, files, handles)):
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


    replace_once(
        files,
        """#include <unistd.h>
#include <copyfile.h>
""",
        """#include <unistd.h>
""",
    )
    replace_once(
        files,
        """#define INVALID_HANDLE 0xFFFFFFFFFFFFFFFFull
""",
        """static int copy_path_data_stat(const char *src, const char *dst) {
    int in = -1, out = -1, result = -1, saved = 0;
    struct stat st;
    if ((in = open(src, O_RDONLY)) < 0) return -1;
    if (fstat(in, &st) != 0) { saved = errno; goto done; }
    out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, st.st_mode & 07777);
    if (out < 0) { saved = errno; goto done; }
    char buf[64 * 1024];
    for (;;) {
        ssize_t n = read(in, buf, sizeof buf);
        if (n == 0) break;
        if (n < 0) {
            if (errno == EINTR) continue;
            saved = errno;
            goto done;
        }
        ssize_t off = 0;
        while (off < n) {
            ssize_t written = write(out, buf + off, (size_t)(n - off));
            if (written < 0) {
                if (errno == EINTR) continue;
                saved = errno;
                goto done;
            }
            off += written;
        }
    }
    if (fchmod(out, st.st_mode & 07777) != 0) { saved = errno; goto done; }
    {
        const struct timespec times[2] = { st.st_atimespec, st.st_mtimespec };
        if (futimens(out, times) != 0) { saved = errno; goto done; }
    }
    result = 0;
done:
    if (out >= 0 && close(out) != 0 && result == 0) {
        result = -1;
        saved = errno;
    }
    if (in >= 0) close(in);
    if (result != 0 && saved) errno = saved;
    return result;
}

#define INVALID_HANDLE 0xFFFFFFFFFFFFFFFFull
""",
    )
    replace_once(
        files,
        """        else if (errno == EXDEV && (fl & 2) && !copyfile(s, d, NULL, COPYFILE_ALL) && !unlink(s)) ok = 1;
""",
        """        else if (errno == EXDEV && (fl & 2) && !copy_path_data_stat(s, d) && !unlink(s)) ok = 1;
""",
    )
    replace_once(
        files,
        """        else if (copyfile(s, d, NULL, COPYFILE_DATA | COPYFILE_STAT)) set_last_error(errno_err(errno, d));
""",
        """        else if (copy_path_data_stat(s, d)) set_last_error(errno_err(errno, d));
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
        """static void deadline(struct timespec *ts, uint32_t ms) {
""",
        """static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static void deadline(struct timespec *ts, uint32_t ms) {
""",
    )
    replace_once(
        handles,
        """extern void cocoa_pump(int wait_ms);
""",
        """static void cocoa_pump(int wait_ms) { (void)wait_ms; }
""",
    )
    replace_once(
        handles,
        """    int on_main = pthread_main_np();
""",
        """    int on_main = 0;  // PS5 has no AppKit main-run-loop ownership.
""",
    )
    replace_once(
        handles,
        """            uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
""",
        """            uint64_t now = monotonic_ns();
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
    print("PS5 Win64 runtime portability edits applied: system.c window.c kernel32.c files.c handles.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
