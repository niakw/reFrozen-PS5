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


def replace_between_once(
    path: Path, start: str, end: str, replacement: str
) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise PatchError(
            f"{path.name}: expected unique block markers "
            f"{start!r} / {end!r}"
        )
    begin = text.index(start)
    finish = text.index(end, begin)
    if finish <= begin:
        raise PatchError(f"{path.name}: invalid block marker order")
    path.write_text(
        text[:begin] + replacement + text[finish:],
        encoding="utf-8",
    )


def patch_runtime(runtime: Path) -> None:
    runtime = runtime.resolve()
    if not runtime.is_dir():
        raise PatchError("runtime root is not a directory")

    system = runtime / "system.c"
    window = runtime / "window.c"
    kernel32 = runtime / "kernel32.c"
    files = runtime / "files.c"
    handles = runtime / "handles.c"
    pdh = runtime / "pdh.c"
    fiber = runtime / "fiber.c"
    if not all(path.is_file() for path in (system, window, kernel32, files, handles, pdh, fiber)):
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


    replace_once(
        handles,
        """#include <dispatch/dispatch.h>
""",
        """#include <signal.h>
""",
    )
    replace_once(
        handles,
        """static void timer_close(HObj *o) {
    if (o->data) { dispatch_source_cancel(o->data); dispatch_release(o->data); o->data = NULL; }
}
static void timer_fire(void *p) {
    HObj *o = p;
    pthread_mutex_lock(&hmu); o->state = 1; h_wake(o); pthread_mutex_unlock(&hmu);
}
""",
        """typedef struct {
    pthread_mutex_t mu;
    timer_t id;
    HObj *owner;
} TimerData;

static void timer_close(HObj *o) {
    TimerData *t = o->data;
    if (!t) return;
    pthread_mutex_lock(&t->mu);
    t->owner = NULL;
    pthread_mutex_unlock(&t->mu);
    timer_delete(t->id);
    // A SIGEV_THREAD callback may already have been scheduled. Keep the tiny
    // TimerData allocation alive until process exit so such a callback can
    // safely observe owner == NULL instead of dereferencing freed storage.
    o->data = NULL;
}
static void timer_fire(union sigval value) {
    TimerData *t = value.sival_ptr;
    if (!t) return;
    pthread_mutex_lock(&t->mu);
    HObj *o = t->owner;
    if (o) {
        pthread_mutex_lock(&hmu);
        o->state = 1;
        h_wake(o);
        pthread_mutex_unlock(&hmu);
    }
    pthread_mutex_unlock(&t->mu);
}
static uint64_t make_timer(int manual) {
    HObj *o = h_alloc(HT_TIMER);
    TimerData *t = calloc(1, sizeof *t);
    if (!o || !t) { free(o); free(t); return 0; }
    pthread_mutex_init(&t->mu, NULL);
    t->owner = o;
    struct sigevent ev;
    memset(&ev, 0, sizeof ev);
    ev.sigev_notify = SIGEV_THREAD;
    ev.sigev_value.sival_ptr = t;
    ev.sigev_notify_function = timer_fire;
    if (timer_create(CLOCK_MONOTONIC, &ev, &t->id) != 0) {
        pthread_mutex_destroy(&t->mu);
        free(t);
        free(o);
        return 0;
    }
    o->manual = manual;
    o->data = t;
    o->close = timer_close;
    return h_new(o);
}
""",
    )
    replace_once(
        handles,
        """void I_kernel32_dll_CreateWaitableTimerA(CPU *c) { HObj *o = h_alloc(HT_TIMER); o->manual = (int)A1 != 0; o->close = timer_close; RET(h_new(o)); }
void I_kernel32_dll_CreateWaitableTimerW(CPU *c) { I_kernel32_dll_CreateWaitableTimerA(c); }
void I_kernel32_dll_CreateWaitableTimerExW(CPU *c) { HObj *o = h_alloc(HT_TIMER); o->manual = (uint32_t)A2 & 1; o->close = timer_close; RET(h_new(o)); }
""",
        """void I_kernel32_dll_CreateWaitableTimerA(CPU *c) { RET(make_timer((int)A1 != 0)); }
void I_kernel32_dll_CreateWaitableTimerW(CPU *c) { I_kernel32_dll_CreateWaitableTimerA(c); }
void I_kernel32_dll_CreateWaitableTimerExW(CPU *c) { RET(make_timer(((uint32_t)A2 & 1) != 0)); }
""",
    )
    replace_once(
        handles,
        """    pthread_mutex_lock(&hmu);
    timer_close(o);
    o->state = 0;
    dispatch_source_t s = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, DISPATCH_TIMER_STRICT,
                                                 dispatch_get_global_queue(QOS_CLASS_USER_INTERACTIVE, 0));
    dispatch_set_context(s, o);
    dispatch_source_set_event_handler_f(s, timer_fire);
    dispatch_source_set_timer(s, dispatch_time(DISPATCH_TIME_NOW, ns), period ? (uint64_t)period * 1000000ull : DISPATCH_TIME_FOREVER, 0);
    o->data = s;
    pthread_mutex_unlock(&hmu);
    dispatch_resume(s);
    RET(1);
""",
        """    if (ns <= 0) ns = 1;
    TimerData *t = o->data;
    if (!t) { set_last_error(6); RET(0); return; }
    struct itimerspec spec;
    memset(&spec, 0, sizeof spec);
    spec.it_value.tv_sec = ns / 1000000000ll;
    spec.it_value.tv_nsec = ns % 1000000000ll;
    if (period) {
        uint64_t pns = (uint64_t)period * 1000000ull;
        spec.it_interval.tv_sec = (time_t)(pns / 1000000000ull);
        spec.it_interval.tv_nsec = (long)(pns % 1000000000ull);
    }
    pthread_mutex_lock(&hmu);
    o->state = 0;
    pthread_mutex_unlock(&hmu);
    if (timer_settime(t->id, 0, &spec, NULL) != 0) { RET(0); return; }
    RET(1);
""",
    )
    replace_once(
        handles,
        """    pthread_mutex_lock(&hmu); timer_close(o); pthread_mutex_unlock(&hmu);
    RET(1);
""",
        """    TimerData *t = o->data;
    if (!t) { RET(0); return; }
    struct itimerspec spec;
    memset(&spec, 0, sizeof spec);
    if (timer_settime(t->id, 0, &spec, NULL) != 0) { RET(0); return; }
    RET(1);
""",
    )


    replace_once(
        pdh,
        """#include <mach/mach.h>
""",
        """#include <sys/resource.h>
#include <sys/sysctl.h>
""",
    )
    replace_once(
        pdh,
        """void I_pdh_dll_PdhCollectQueryData(CPU *c) {
    Query *q = PTR(A0);
    natural_t n = 0; processor_info_array_t info; mach_msg_type_number_t cnt;
    if (!q || host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO, &n, &info, &cnt) != KERN_SUCCESS) { RET(0); return; }
    pthread_mutex_lock(&pmu);
    double sum = 0; int m = (int)n < MAXCORES ? (int)n : MAXCORES;
    for (int i = 0; i < m; i++) {
        const integer_t *t = info + CPU_STATE_MAX * i;
        uint64_t busy = (uint32_t)t[CPU_STATE_USER] + (uint32_t)t[CPU_STATE_SYSTEM] + (uint32_t)t[CPU_STATE_NICE];
        uint64_t total = busy + (uint32_t)t[CPU_STATE_IDLE];
        if (q->have && total > q->total[i]) q->load[i] = 100.0 * (double)(busy - q->busy[i]) / (double)(total - q->total[i]);
        q->busy[i] = busy; q->total[i] = total;
        sum += q->load[i];
    }
    q->load[MAXCORES] = m ? sum / m : 0;
    q->have = 1; q->ncores = m;
    pthread_mutex_unlock(&pmu);
    vm_deallocate(mach_task_self(), (vm_address_t)info, cnt * sizeof(integer_t));
    RET(0);
}
""",
        """static int sample_cpu_ticks(long **out, int *ncores) {
    size_t bytes = 0;
    if (sysctlbyname("kern.cp_times", NULL, &bytes, NULL, 0) == 0 && bytes >= CPUSTATES * sizeof(long)) {
        long *ticks = malloc(bytes);
        if (ticks && sysctlbyname("kern.cp_times", ticks, &bytes, NULL, 0) == 0) {
            *out = ticks;
            *ncores = (int)(bytes / (CPUSTATES * sizeof(long)));
            return 1;
        }
        free(ticks);
    }
    long one[CPUSTATES];
    bytes = sizeof one;
    if (sysctlbyname("kern.cp_time", one, &bytes, NULL, 0) == 0 && bytes >= sizeof one) {
        long *ticks = malloc(sizeof one);
        if (!ticks) return 0;
        memcpy(ticks, one, sizeof one);
        *out = ticks;
        *ncores = 1;
        return 1;
    }
    return 0;
}

void I_pdh_dll_PdhCollectQueryData(CPU *c) {
    Query *q = PTR(A0);
    long *info = NULL; int n = 0;
    if (!q || !sample_cpu_ticks(&info, &n)) { RET(0); return; }
    pthread_mutex_lock(&pmu);
    double sum = 0; int m = n < MAXCORES ? n : MAXCORES;
    for (int i = 0; i < m; i++) {
        const long *t = info + CPUSTATES * i;
        uint64_t busy = (uint64_t)t[CP_USER] + (uint64_t)t[CP_NICE] + (uint64_t)t[CP_SYS] + (uint64_t)t[CP_INTR];
        uint64_t total = busy + (uint64_t)t[CP_IDLE];
        if (q->have && total > q->total[i]) q->load[i] = 100.0 * (double)(busy - q->busy[i]) / (double)(total - q->total[i]);
        q->busy[i] = busy; q->total[i] = total;
        sum += q->load[i];
    }
    q->load[MAXCORES] = m ? sum / m : 0;
    q->have = 1; q->ncores = m;
    pthread_mutex_unlock(&pmu);
    free(info);
    RET(0);
}
""",
    )


    replace_once(
        fiber,
        """// Win32 fibers on arm64. A fiber owns a native stack (for the nested C frames of translated code)
""",
        """// Win32 fibers on x86-64 PS5. A fiber owns a native stack (for the nested C frames of translated code)
""",
    )
    replace_between_once(
        fiber,
        "__attribute__((naked)) static void swap_ctx",
        "static __thread Fiber *cur_fiber;",
        r"""__attribute__((naked)) static void swap_ctx(uint64_t *save_sp, uint64_t new_sp) {
    __asm__ volatile(
        "pushq %rbx\n"
        "pushq %rbp\n"
        "pushq %r12\n"
        "pushq %r13\n"
        "pushq %r14\n"
        "pushq %r15\n"
        "movq %rsp, (%rdi)\n"
        "movq %rsi, %rsp\n"
        "popq %r15\n"
        "popq %r14\n"
        "popq %r13\n"
        "popq %r12\n"
        "popq %rbp\n"
        "popq %rbx\n"
        "retq\n");
}

""",
    )
    replace_between_once(
        fiber,
        '    // initial native frame: swap_ctx "returns" into fiber_entry\n',
        "    f->host_sp = sp;\n",
        """    // Initial SysV x86-64 frame for swap_ctx:
    // r15,r14,r13,r12,rbp,rbx,return-address. After six pops + ret,
    // fiber_entry starts with the ABI-required rsp % 16 == 8.
    uint64_t top = G(f->host_stack) + f->host_size;
    uint64_t sp = (top - 56) & ~0xFull;
    memset(PTR(sp), 0, 56);
    wr64(sp + 48, G(fiber_entry));
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
    print("PS5 Win64 runtime portability edits applied: system.c window.c kernel32.c files.c handles.c pdh.c fiber.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
