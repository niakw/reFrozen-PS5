#!/usr/bin/env python3
"""Apply fail-closed PS5 guest-memory edits to pinned NightSight runtime/rt.c."""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        first = old.splitlines()[0] if old.splitlines() else "<empty>"
        raise PatchError(
            f"{path.name}: fragment {first!r} expected once, found {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_rt(runtime: Path) -> None:
    rt = runtime.resolve() / "rt.c"
    if not rt.is_file():
        raise PatchError("pinned runtime is missing rt.c")

    replace_once(
        rt,
        """#include <spawn.h>
#include <dlfcn.h>
#include <sys/ucontext.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <crt_externs.h>
#include <unistd.h>
""",
        """#include <sys/ucontext.h>
#include <time.h>
#include <unistd.h>

#include "win64_memory_bridge_ps5.h"
""",
    )
    replace_once(
        rt,
        """// ---------------- logging ----------------
// RT_LOGTIME=1: prefix lines with seconds since start (for timing startup phases)
void rt_log(const char *fmt, ...) {
    static int timed = -1; static uint64_t t0;
    if (timed < 0) { timed = getenv("RT_LOGTIME") != NULL; t0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW); }
    if (timed) fprintf(stderr, "%8.3f ", (clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0) / 1e9);
""",
        """// ---------------- logging ----------------
// RT_LOGTIME=1: prefix lines with seconds since start (for timing startup phases)
static uint64_t monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
void rt_log(const char *fmt, ...) {
    static int timed = -1; static uint64_t t0;
    if (timed < 0) { timed = getenv("RT_LOGTIME") != NULL; t0 = monotonic_ns(); }
    if (timed) fprintf(stderr, "%8.3f ", (monotonic_ns() - t0) / 1e9);
""",
    )

    replace_once(
        rt,
        """// ---------------- guest image ----------------
// Reserve the guest image range before the host allocator can place an arena there.
static int guest_reserved;
// The guest image range is part of the executable: a zero-fill segment that the Makefile links at
// 0x140000000 (-segaddr __GUEST). dyld maps it before any allocator runs, so nothing else can land
// there. With ASLR on it slides elsewhere, and rt_reexec_fixed_layout() restarts without ASLR.
#define GUEST_SEGMENT_SIZE 0x18000000
__asm__(".zerofill __GUEST,__image,_rt_guest_segment," "0x18000000" ",14");
extern char rt_guest_segment[];
__attribute__((constructor(101))) static void reserve_guest_range(void) {
    if ((uint64_t)(uintptr_t)rt_guest_segment == gimage_base && gimage_size <= GUEST_SEGMENT_SIZE) { guest_reserved = 1; return; }
    void *want = (void *)(uintptr_t)gimage_base;
    void *p = mmap(want, gimage_size, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (p == want) { guest_reserved = 1; return; }
    if (p != MAP_FAILED) munmap(p, gimage_size);
}
""",
        """// ---------------- guest image ----------------
// PS5 direct memory must be identity-mapped at the PE preferred VA because
// translated code embeds absolute guest addresses.
#define PS5_GUEST_ALIGNMENT 0x4000ull
static int map_guest_region(uint64_t base, uint64_t size, const char *label) {
    struct refrozen_ps5_guest_map_info info;
    int rc = refrozen_ps5_map_guest_rw(base, size, PS5_GUEST_ALIGNMENT, &info);
    if (rc == REFROZEN_PS5_GUEST_MAP_OK) return 1;
    rt_log("[rt] PS5 map %s at 0x%llx size 0x%llx failed: code=%d native=%d map=%d alloc=%d abort=%d\n",
           label, (unsigned long long)base, (unsigned long long)size, rc,
           info.native_status, info.native_map_code, info.native_allocate_code,
           info.requires_process_abort);
    if (info.requires_process_abort) abort();
    return 0;
}
static void release_guest_region(uint64_t base, const char *label) {
    int rc = refrozen_ps5_release_guest_rw(base);
    if (rc != REFROZEN_PS5_GUEST_RELEASE_OK)
        rt_log("[rt] PS5 release %s at 0x%llx failed: code=%d\n",
               label, (unsigned long long)base, rc);
}
""",
    )
    replace_once(
        rt,
        """    void *want = (void *)(uintptr_t)gimage_base;
    // The range was reserved by reserve_guest_range() at startup; map over that reservation only.
    void *p = guest_reserved ? mmap(want, gimage_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0)
                             : mmap(want, gimage_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (p != want) {
        rt_log("[rt] guest image range 0x%llx is not free (got %p); mappings in the way:\n", (unsigned long long)gimage_base, p);
        mach_vm_address_t a = gimage_base; mach_vm_size_t sz; vm_region_basic_info_data_64_t info; mach_msg_type_number_t cnt; mach_port_t obj;
        while (a < gimage_base + gimage_size) {
            cnt = VM_REGION_BASIC_INFO_COUNT_64;
            if (mach_vm_region(mach_task_self(), &a, &sz, VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info, &cnt, &obj) != KERN_SUCCESS) break;
            if (a >= gimage_base + gimage_size) break;
            rt_log("    %llx-%llx prot %d\n", (unsigned long long)a, (unsigned long long)(a + sz), info.protection);
            a += sz;
        }
        rt_log("    RT_FIXED_LAYOUT=%s\n", getenv("RT_FIXED_LAYOUT") ? getenv("RT_FIXED_LAYOUT") : "(unset)");
        exit(1);
    }
""",
        """    if (!map_guest_region(gimage_base, gimage_size, "exe")) exit(1);
    void *p = (void *)(uintptr_t)gimage_base;
""",
    )

    replace_once(
        rt,
        """// ---------------- translated DLLs ----------------
// DLL images live in a second zero-fill segment (-segaddr __GUESTDLL 0x180000000), the usual 64-bit DLL base.
#define DLL_SEGMENT_BASE 0x180000000ull
#define DLL_SEGMENT_SIZE 0x4000000ull
__asm__(".zerofill __GUESTDLL,__images,_rt_dll_segment," "0x4000000" ",14");
extern char rt_dll_segment[];
""",
        """// ---------------- translated DLLs ----------------
// Each translated DLL receives its own exact PS5 direct-memory mapping at
// the base selected by the Win64 translator (preferred or explicitly rebased).
""",
    )
    replace_once(
        rt,
        """    void *want = PTR(m->base);
    int in_seg = (uint64_t)(uintptr_t)rt_dll_segment == DLL_SEGMENT_BASE && m->base >= DLL_SEGMENT_BASE && m->base + m->size <= DLL_SEGMENT_BASE + DLL_SEGMENT_SIZE;
    void *p = mmap(want, m->size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | (in_seg ? MAP_FIXED : 0), -1, 0);
    if (p != want) { rt_log("[rt] cannot map %s at 0x%llx (got %p)\n", m->name, (unsigned long long)m->base, p); if (p != MAP_FAILED) munmap(p, m->size); return 0; }
""",
        """    if (!map_guest_region(m->base, m->size, m->name)) return 0;
    void *p = PTR(m->base);
""",
    )
    replace_once(
        rt,
        """    FILE *f = fopen(host_path, "rb");
    if (!f) { rt_log("[rt] %s: %s not found\n", m->name, host_path); return 0; }
    if (fread(p, 1, 0x1000, f) != 0x1000) { fclose(f); return 0; }
""",
        """    FILE *f = fopen(host_path, "rb");
    if (!f) { rt_log("[rt] %s: %s not found\n", m->name, host_path); release_guest_region(m->base, m->name); return 0; }
    if (fread(p, 1, 0x1000, f) != 0x1000) { fclose(f); release_guest_region(m->base, m->name); return 0; }
""",
    )
    replace_once(
        rt,
        """        if (n && fread(PTR(sc->va), 1, n, f) != n) { rt_log("[rt] %s: short read in %s\n", m->name, sc->name); fclose(f); return 0; }
""",
        """        if (n && fread(PTR(sc->va), 1, n, f) != n) { rt_log("[rt] %s: short read in %s\n", m->name, sc->name); fclose(f); release_guest_region(m->base, m->name); return 0; }
""",
    )

    replace_once(
        rt,
        """// The translated code needs the guest image at 0x140000000. With ASLR the host binary can land
// there, so the process re-executes itself once (same PID) with ASLR disabled: the host binary then
// loads at its link address 0x100000000, well below the guest image.
#ifndef _POSIX_SPAWN_DISABLE_ASLR
#define _POSIX_SPAWN_DISABLE_ASLR 0x0100
#endif
void rt_reexec_fixed_layout(char **argv) {
    const char *v = getenv("RT_FIXED_LAYOUT");
    int tries = v ? atoi(v) : 0;
    if (tries && (guest_reserved || tries >= 4)) return;
    char buf[8]; snprintf(buf, sizeof buf, "%d", tries + 1);
    setenv("RT_FIXED_LAYOUT", buf, 1);
    posix_spawnattr_t a; posix_spawnattr_init(&a);
    posix_spawnattr_setflags(&a, POSIX_SPAWN_SETEXEC | _POSIX_SPAWN_DISABLE_ASLR);
    char path[4096]; uint32_t n = sizeof path;
    extern int _NSGetExecutablePath(char *, uint32_t *);
    if (_NSGetExecutablePath(path, &n)) return;
    posix_spawn(NULL, path, NULL, &a, argv, *_NSGetEnviron());
    rt_log("[rt] re-exec without ASLR failed; continuing\n");
}
""",
        """// PS5 guest VAs are reserved/mapped explicitly through the direct-memory
// bridge. There is no Mach-O dyld layout to repair with a no-ASLR re-exec.
void rt_reexec_fixed_layout(char **argv) { (void)argv; }
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    try:
        patch_rt(args.runtime)
    except (OSError, PatchError) as exc:
        parser.error(str(exc))
    print("PS5 Win64 rt.c exact-VA/direct-memory edits applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
