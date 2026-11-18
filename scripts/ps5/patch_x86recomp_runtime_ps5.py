#!/usr/bin/env python3
"""Apply fail-closed PS5 host portability edits to patched x86recomp runtime.

This runs *after* the generic reFrozen patch series. It deliberately keeps
PS5-only assumptions out of patches/x86recomp, whose earlier patches are also
used by upstream macOS/Linux development.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrence(s), found {count}: {old[:80]!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")



def patch_monotonic_timing(rt: Path) -> None:
    """Remove SDL timing-only dependencies from the PS5 Win32 runtime."""
    targets = (
        ("hle/ddraw.cpp", 2, 0),
        ("hle/present.cpp", 0, 2),
        ("hle/user32_window.cpp", 6, 0),
    )
    for relative, ticks_ms, ticks_ns in targets:
        path = rt / relative
        text = path.read_text(encoding="utf-8")
        marker = '#include "runtime/platform.h"\n'
        if marker not in text:
            anchor = '#include "runtime/log.h"\n'
            if text.count(anchor) != 1:
                raise SystemExit(
                    f"{path}: expected one runtime/log.h include, found {text.count(anchor)}"
                )
            text = text.replace(anchor, anchor + marker)
        if text.count("SDL_GetTicks()") != ticks_ms:
            raise SystemExit(
                f"{path}: expected {ticks_ms} SDL_GetTicks() call(s), "
                f"found {text.count('SDL_GetTicks()')}"
            )
        if text.count("SDL_GetTicksNS()") != ticks_ns:
            raise SystemExit(
                f"{path}: expected {ticks_ns} SDL_GetTicksNS() call(s), "
                f"found {text.count('SDL_GetTicksNS()')}"
            )
        text = text.replace(
            "SDL_GetTicks()", "(platform::MonotonicNs() / 1000000ULL)"
        )
        text = text.replace("SDL_GetTicksNS()", "platform::MonotonicNs()")
        path.write_text(text, encoding="utf-8")



def patch_win32_raw_input_hooks(rt: Path) -> None:
    """Expose native PS5 pad events through SwARc's existing RawInput sink."""
    path = rt / "hle" / "user32_input.cpp"
    anchor = """void EmitRawInput(RawInput::Kind kind, uint8_t code, int32_t value) {
  if (RawInputSink sink = g_raw_sink) sink({kind, code, value, TickCount()});
}

"""
    hooks = """void EmitRawInput(RawInput::Kind kind, uint8_t code, int32_t value) {
  if (RawInputSink sink = g_raw_sink) sink({kind, code, value, TickCount()});
}

// Native PS5 pad bridge entry points. These intentionally feed DirectInput's
// existing RawInput path only; window-message state remains owned by user32.
extern "C" void di_key(uint32_t scan, int ext, int down) {
  const uint8_t dik = uint8_t(scan | (ext ? 0x80u : 0u));
  EmitRawInput(RawInput::Key, dik, down ? 1 : 0);
}
extern "C" void di_mouse_move(int dx, int dy) {
  if (dx) EmitRawInput(RawInput::MouseX, 0, dx);
  if (dy) EmitRawInput(RawInput::MouseY, 0, dy);
}
extern "C" void di_mouse_wheel(int dz) {
  if (dz) EmitRawInput(RawInput::Wheel, 0, dz);
}
extern "C" void di_mouse_button(int button, int down) {
  if (button < 0 || button > 7) return;
  EmitRawInput(RawInput::MouseButton, uint8_t(button), down ? 1 : 0);
}

"""
    replace_exact(path, anchor, hooks)


def apply(root: Path) -> None:
    rt = root / "src" / "runtime"
    if not rt.is_dir():
        raise SystemExit(f"runtime directory not found: {rt}")

    patch_monotonic_timing(rt)

    patch_win32_raw_input_hooks(rt)

    guest = rt / "guest_memory.cpp"
    replace_exact(
        guest,
        "constexpr int kReserveFlags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE;",
        """#ifdef MAP_NORESERVE
constexpr int kReserveFlags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE;
#else
constexpr int kReserveFlags = MAP_PRIVATE | MAP_ANONYMOUS;
#endif""",
    )

    dispatch = rt / "dispatch.cpp"
    replace_exact(
        dispatch,
        '  char name[32] = "?";\n'
        '  pthread_getname_np(pthread_self(), name, sizeof name);\n',
        '  char name[32] = "?";\n'
        '#if defined(__linux__) || defined(__APPLE__)\n'
        '  pthread_getname_np(pthread_self(), name, sizeof name);\n'
        '#else\n'
        '  std::snprintf(name, sizeof name, "host-%04X",\n'
        '                CurrentThread() ? CurrentThread()->tid : 0u);\n'
        '#endif\n',
    )
    replace_exact(
        dispatch,
        "MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);",
        "MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);",
    )
    replace_exact(
        dispatch,
        "#include <execinfo.h>\n",
        """#if defined(__linux__) || defined(__APPLE__)
#include <execinfo.h>
#define RECOMP_HAVE_EXECINFO 1
#else
#define RECOMP_HAVE_EXECINFO 0
#endif
""",
    )
    replace_exact(
        dispatch,
        """    std::fprintf(stderr, "  host backtrace:\\n");
    std::fflush(stderr);
    void* frames[64];
    int nf = backtrace(frames, 64);
    backtrace_symbols_fd(frames, nf, 2);
""",
        """    std::fprintf(stderr, "  host backtrace:\\n");
    std::fflush(stderr);
#if RECOMP_HAVE_EXECINFO
    void* frames[64];
    int nf = backtrace(frames, 64);
    backtrace_symbols_fd(frames, nf, 2);
#else
    std::fprintf(stderr, "    (host backtrace unavailable on this platform)\\n");
#endif
""",
    )
    replace_exact(
        dispatch,
        """  if (fc.caller) {
    void* caller = reinterpret_cast<void*>(fc.caller);
    backtrace_symbols_fd(&caller, 1, 2);
  }
  void* frames[48];
  int nf = backtrace(frames, 48);
  backtrace_symbols_fd(frames, nf, 2);
""",
        """#if RECOMP_HAVE_EXECINFO
  if (fc.caller) {
    void* caller = reinterpret_cast<void*>(fc.caller);
    backtrace_symbols_fd(&caller, 1, 2);
  }
  void* frames[48];
  int nf = backtrace(frames, 48);
  backtrace_symbols_fd(frames, nf, 2);
#else
  const char no_bt[] = "  host backtrace unavailable on this platform\\n";
  (void)!write(2, no_bt, sizeof no_bt - 1);
#endif
""",
    )

    socket = rt / "hle" / "wsock32_socket.cpp"
    replace_exact(socket, "SO_LINGER_SEC", "SO_LINGER", expected=2)

    watchdog = rt / "watchdog.cpp"
    replace_exact(
        watchdog,
        "#include <execinfo.h>\n",
        """#if defined(__linux__) || defined(__APPLE__)
#include <execinfo.h>
#define RECOMP_WATCHDOG_HAVE_EXECINFO 1
#else
#define RECOMP_WATCHDOG_HAVE_EXECINFO 0
#endif
""",
    )
    replace_exact(
        watchdog,
        """    void* frames[512];
    int n = backtrace(frames, 512);
    backtrace_symbols_fd(frames, n, fd);
""",
        """#if RECOMP_WATCHDOG_HAVE_EXECINFO
    void* frames[512];
    int n = backtrace(frames, 512);
    backtrace_symbols_fd(frames, n, fd);
#else
    WriteAll(fd, "(host backtrace unavailable on this platform)\\n");
#endif
""",
    )
    replace_exact(
        watchdog,
        """  // backtrace() loads libgcc on first use, which must not happen inside
  // the signal handler.
  void* f[2];
  backtrace(f, 2);
""",
        """#if RECOMP_WATCHDOG_HAVE_EXECINFO
  // backtrace() loads libgcc on first use, which must not happen inside
  // the signal handler.
  void* f[2];
  backtrace(f, 2);
#endif
""",
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("x86recomp_root", type=Path)
    args = p.parse_args()
    apply(args.x86recomp_root.resolve())
    print("REFROZEN_PS5_X86RECOMP_HOST_PATCH pass=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
