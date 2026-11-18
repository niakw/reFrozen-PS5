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
  Ps5User32Key(scan, ext, down);
}
extern "C" void di_mouse_move(int dx, int dy) {
  if (dx) EmitRawInput(RawInput::MouseX, 0, dx);
  if (dy) EmitRawInput(RawInput::MouseY, 0, dy);
  Ps5User32MouseMove(dx, dy);
}
extern "C" void di_mouse_wheel(int dz) {
  if (dz) EmitRawInput(RawInput::Wheel, 0, dz);
  Ps5User32MouseWheel(dz);
}
extern "C" void di_mouse_button(int button, int down) {
  if (button < 0 || button > 7) return;
  EmitRawInput(RawInput::MouseButton, uint8_t(button), down ? 1 : 0);
  Ps5User32MouseButton(button, down);
}

"""
    replace_exact(path, anchor, hooks)



def patch_win32_audio_output(rt: Path) -> None:
    """Route SwARc's mixer to the native PS5 48 kHz threaded output driver."""
    header = rt / "audio" / "mixer.h"
    replace_exact(header, "struct SDL_AudioStream;\n",
                  "struct refrozen_ps5_win32_audio_driver;\n")
    replace_exact(
        header,
        "  SDL_AudioStream* stream_ = nullptr;\n",
        "  refrozen_ps5_win32_audio_driver* stream_ = nullptr;\n",
    )

    source = rt / "audio" / "mixer.cpp"
    replace_exact(
        source,
        "#include <SDL3/SDL.h>\n",
        '#include "ps5_win32_audio_driver.h"\n',
    )
    replace_exact(
        source,
        """void SDLCALL AudioCallback(void* ud, SDL_AudioStream* s, int additional, int) {
  auto* m = static_cast<Mixer*>(ud);
  float buf[kChunk * 2];
  int frames = additional / int(2 * sizeof(float));
  while (frames > 0) {
    int n = std::min(frames, kChunk);
    m->Mix(buf, n);
    SDL_PutAudioStreamData(s, buf, n * int(2 * sizeof(float)));
    frames -= n;
  }
}
""",
        """void Ps5AudioCallback(void* ud, float* out, int frames) {
  static_cast<Mixer*>(ud)->Mix(out, frames);
}
""",
    )
    replace_exact(
        source,
        """bool Mixer::Open(int rate) {
  if (stream_) return true;
  if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
    WarnF("audio: SDL audio init failed: %s\\n", SDL_GetError());
    return false;
  }
  SDL_AudioSpec spec{SDL_AUDIO_F32, 2, rate};
  stream_ = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec,
                                      AudioCallback, this);
  if (!stream_) {
    WarnF("audio: cannot open a playback device: %s\\n", SDL_GetError());
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
    return false;
  }
  Init(rate);  // the device starts paused: no Mix runs yet
  SDL_ResumeAudioStreamDevice(stream_);
  WarnF("audio: %d Hz stereo on SDL driver '%s'\\n", rate,
        SDL_GetCurrentAudioDriver());
  return true;
}
""",
        """bool Mixer::Open(int rate) {
  if (stream_) return true;
  Init(rate);
  stream_ = refrozen_ps5_win32_audio_driver_start(
      uint32_t(rate), this, Ps5AudioCallback);
  if (!stream_) {
    WarnF("audio: cannot open PS5 48 kHz playback for %d Hz source\\n", rate);
    reverb_.Close();
    rate_ = 0;
    return false;
  }
  WarnF("audio: %d Hz stereo -> PS5 48000 Hz native output\\n", rate);
  return true;
}
""",
    )
    replace_exact(
        source,
        """void Mixer::Close() {
  if (stream_) {
    SDL_DestroyAudioStream(stream_);  // stops the callback first
    stream_ = nullptr;
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
  }
  reverb_.Close();
}
""",
        """void Mixer::Close() {
  if (stream_) {
    refrozen_ps5_win32_audio_driver_stop(stream_);
    stream_ = nullptr;
  }
  reverb_.Close();
}
""",
    )



def patch_win32_user32_pad_events(rt: Path) -> None:
    """Feed native pad events into Win32 key state and message queues."""
    header = rt / "hle" / "user32_window.h"
    header_anchor = """void PumpHostEvents();

"""
    header_insert = """void PumpHostEvents();

// Native PS5 input events. These complement DirectInput RawInput by updating
// Win32 key/mouse state and posting WM_* messages to the active top-level HWND.
// Call from the runtime's main thread.
void Ps5User32Key(uint32_t scan, int ext, int down);
void Ps5User32MouseMove(int dx, int dy);
void Ps5User32MouseWheel(int dz);
void Ps5User32MouseButton(int button, int down);

"""
    replace_exact(header, header_anchor, header_insert)

    source = rt / "hle" / "user32_window.cpp"
    source_anchor = """}  // namespace

void PumpHostEvents() {
"""
    source_insert = r"""}  // namespace

namespace {

uint32_t Ps5InputHwnd() {
  std::lock_guard<std::recursive_mutex> l(g_mu);
  if (g_focus && Win(g_focus)) return g_focus;
  if (g_active && Win(g_active)) return g_active;
  for (const auto& [hwnd, w] : g_windows)
    if (!w.destroyed && !(w.style & WS_CHILD) && w.visible) return hwnd;
  for (const auto& [hwnd, w] : g_windows)
    if (!w.destroyed && !(w.style & WS_CHILD)) return hwnd;
  return 0;
}

uint8_t Ps5VkForScan(uint8_t scan, bool ext) {
  for (unsigned vk = 1; vk < 256; ++vk) {
    bool candidate_ext = false;
    const uint8_t candidate =
        ScanCodeForVk(static_cast<uint8_t>(vk), &candidate_ext);
    if (candidate == scan && candidate_ext == ext)
      return static_cast<uint8_t>(vk);
  }
  return 0;
}

}  // namespace

void Ps5User32Key(uint32_t scan_value, int ext_value, int down_value) {
  if (!OnMainThread()) {
    WarnF("PS5 user32 key input outside main thread; ignored\n");
    return;
  }
  const uint32_t hwnd = Ps5InputHwnd();
  const uint8_t scan = static_cast<uint8_t>(scan_value & 0x7fu);
  const bool ext = ext_value != 0;
  const bool down = down_value != 0;
  const uint8_t vk = Ps5VkForScan(scan, ext);
  if (!hwnd || !vk) return;

  const uint8_t gvk = GenericVk(vk);
  const bool was_down = g_key_down[gvk] != 0;
  SetKey(vk, down);
  SetKey(gvk, down);

  uint32_t lp = 1u | (uint32_t(scan) << 16) | (ext ? 1u << 24 : 0);
  if (!down)
    lp |= 0xC0000000u;
  else if (was_down)
    lp |= 0x40000000u;

  const bool alt = g_key_down[0x12] != 0;
  const bool sys = alt || gvk == 0x79 || gvk == 0x12;
  if (alt) lp |= 1u << 29;

  if (down) {
    const uint32_t mods = (alt ? 1u : 0) |
                          (g_key_down[0x11] ? 2u : 0) |
                          (g_key_down[0x10] ? 4u : 0);
    HotKey match{};
    bool matched = false;
    {
      std::lock_guard<std::recursive_mutex> l(g_mu);
      for (const HotKey& k : g_hotkeys) {
        if (k.vk == gvk && (k.mods & 7) == mods) {
          match = k;
          matched = true;
          break;
        }
      }
    }
    if (matched) {
      PostTo(match.tid,
             Msg{match.hwnd, 0x0312 /* WM_HOTKEY */, match.id,
                 mods | (uint32_t(gvk) << 16), TickCount(),
                 g_mouse_x, g_mouse_y});
      return;
    }
  }

  const uint32_t msg =
      down ? (sys ? WM_SYSKEYDOWN : WM_KEYDOWN)
           : (sys ? WM_SYSKEYUP : WM_KEYUP);
  Post(hwnd, msg, gvk, lp);
}

void Ps5User32MouseMove(int dx, int dy) {
  if (!OnMainThread() || (!dx && !dy)) return;
  const uint32_t hwnd = Ps5InputHwnd();
  if (!hwnd) return;

  int ox = 0, oy = 0, cw = 0, ch = 0;
  WindowOrigin(hwnd, &ox, &oy);
  ClientAreaSize(hwnd, &cw, &ch);
  if (cw <= 0 || ch <= 0) return;

  int x = g_mouse_x - ox;
  int y = g_mouse_y - oy;
  if (x < 0 || x >= cw || y < 0 || y >= ch) {
    x = cw / 2;
    y = ch / 2;
  }
  x = std::clamp(x + dx, 0, cw - 1);
  y = std::clamp(y + dy, 0, ch - 1);
  g_mouse_x = ox + x;
  g_mouse_y = oy + y;
  g_real_x.store(x);
  g_real_y.store(y);
  g_pointer_inside.store(true);
  Post(hwnd, WM_MOUSEMOVE, MouseKeys(), MkLparam(x, y));
}

void Ps5User32MouseWheel(int dz) {
  if (!OnMainThread() || !dz) return;
  const uint32_t hwnd = Ps5InputHwnd();
  if (!hwnd) return;
  const int delta = std::clamp(dz, -32768, 32767);
  Post(hwnd, WM_MOUSEWHEEL,
       MouseKeys() | (uint32_t(uint16_t(int16_t(delta))) << 16),
       MkLparam(g_mouse_x, g_mouse_y));
}

void Ps5User32MouseButton(int button, int down_value) {
  if (!OnMainThread() || button < 0 || button > 2) return;
  const uint32_t hwnd = Ps5InputHwnd();
  if (!hwnd) return;

  static constexpr uint32_t kBase[] = {
      WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN};
  static constexpr uint8_t kVk[] = {0x01, 0x02, 0x04};
  const bool down = down_value != 0;
  const uint8_t vk = kVk[button];
  SetKey(vk, down);

  int ox = 0, oy = 0;
  WindowOrigin(hwnd, &ox, &oy);
  const uint32_t msg = down ? kBase[button] : kBase[button] + 1;
  Post(hwnd, msg, MouseKeys(),
       MkLparam(g_mouse_x - ox, g_mouse_y - oy));
}

void PumpHostEvents() {
"""
    replace_exact(source, source_anchor, source_insert)


def apply(root: Path) -> None:
    rt = root / "src" / "runtime"
    if not rt.is_dir():
        raise SystemExit(f"runtime directory not found: {rt}")

    patch_monotonic_timing(rt)

    patch_win32_raw_input_hooks(rt)

    patch_win32_user32_pad_events(rt)

    patch_win32_audio_output(rt)

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
