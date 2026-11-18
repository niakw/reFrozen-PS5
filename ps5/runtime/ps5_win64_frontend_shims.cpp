// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 replacements for the small Cocoa/GameController surface still consumed
// by NightSight's portable Win64 user32/XInput runtime.
//
// This is a console fullscreen frontend, not a Cocoa emulation layer. Guest
// window geometry/state stays in window.c; these functions only provide the
// host-facing tokens and input bridge that window.c expects.
#include "ps5_dinput_pad_bridge.hpp"
#include "ps5_pad_contract.hpp"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <new>
#include <time.h>

extern "C" {
void rt_log(const char* fmt, ...);
void gamepad_start(void);

std::uint64_t rt_last_surface_hwnd = 0;

void rt_request_screenshot(const char* path) {
  static std::atomic<bool> logged{false};
  if (!logged.exchange(true))
    rt_log("[ps5/frontend] screenshot debug hook unavailable on OpenGL first-launch route\n");
  (void)path;
}
void rt_vk_snapshot_request(void) {}
void rt_vk_skip_next(void) {}

int rt_ps5_graphics_init(void) __attribute__((weak));

int rt_ps5_frontend_init(void) {
  // Input can be initialized before a pad is physically connected; the
  // polling path retries later if the first open fails.
  gamepad_start();
  if (rt_ps5_graphics_init) {
    const int rc = rt_ps5_graphics_init();
    if (rc != 0) {
      rt_log("[ps5/frontend] graphics initialization failed: %d\n", rc);
      return rc;
    }
  }
  return 0;
}
}

namespace {
using namespace refrozen::ps5;
using namespace refrozen::ps5::pad;

struct LogicalWindow {
  std::uint64_t hwnd{};
  int x{}, y{}, w{1920}, h{1080};
  bool visible{false};
  bool minimized{false};
  bool zoomed{true};
  bool titled{false};
  bool resizable{false};
  bool minimizable{false};
  char title[256]{};
};

std::atomic<int> g_window_count{0};
std::atomic<int> g_cursor_x{960};
std::atomic<int> g_cursor_y{540};
std::atomic<bool> g_cursor_visible{true};

std::mutex g_pad_mu;
DinputPadBridge g_pad{};
std::uint32_t g_xinput_packet = 1;
std::uint8_t g_last_xinput[12]{};

bool EnsurePadLocked() {
  if (g_pad.handle >= 0) return true;
  // Retry rather than permanently caching a boot-time failure: controllers
  // can become available after the title has started.
  return OpenDinputPad(&g_pad) == 0;
}

bool ReadPadLocked(Data* out) {
  if (!out || !EnsurePadLocked()) return false;
  Data sample{};
  if (scePadReadState(g_pad.handle, &sample) < 0 || !usable(sample))
    return false;
  *out = sample;
  return true;
}

std::int16_t Axis(std::uint8_t raw, bool invert) {
  int delta = static_cast<int>(raw) - 128;
  if (invert) delta = -delta;
  // Match XInput's asymmetric signed range.
  if (delta < 0)
    return static_cast<std::int16_t>(
        std::max(-32768, delta * 256));
  return static_cast<std::int16_t>(
      std::min(32767, delta * 258));
}

constexpr std::uint16_t kXbUp = 0x0001;
constexpr std::uint16_t kXbDown = 0x0002;
constexpr std::uint16_t kXbLeft = 0x0004;
constexpr std::uint16_t kXbRight = 0x0008;
constexpr std::uint16_t kXbStart = 0x0010;
constexpr std::uint16_t kXbBack = 0x0020;
constexpr std::uint16_t kXbLThumb = 0x0040;
constexpr std::uint16_t kXbRThumb = 0x0080;
constexpr std::uint16_t kXbLShoulder = 0x0100;
constexpr std::uint16_t kXbRShoulder = 0x0200;
constexpr std::uint16_t kXbA = 0x1000;
constexpr std::uint16_t kXbB = 0x2000;
constexpr std::uint16_t kXbX = 0x4000;
constexpr std::uint16_t kXbY = 0x8000;

std::uint16_t XInputButtons(std::uint32_t b) {
  std::uint16_t out = 0;
  if (b & kButtonUp) out |= kXbUp;
  if (b & kButtonDown) out |= kXbDown;
  if (b & kButtonLeft) out |= kXbLeft;
  if (b & kButtonRight) out |= kXbRight;
  if (b & kButtonOptions) out |= kXbStart;
  if (b & kButtonTouchPad) out |= kXbBack;
  if (b & kButtonL3) out |= kXbLThumb;
  if (b & kButtonR3) out |= kXbRThumb;
  if (b & kButtonL1) out |= kXbLShoulder;
  if (b & kButtonR1) out |= kXbRShoulder;
  if (b & kButtonCross) out |= kXbA;
  if (b & kButtonCircle) out |= kXbB;
  if (b & kButtonSquare) out |= kXbX;
  if (b & kButtonTriangle) out |= kXbY;
  return out;
}

void CopyTitle(LogicalWindow* w, const char* title) {
  if (!w) return;
  std::snprintf(w->title, sizeof(w->title), "%s", title ? title : "");
}

}  // namespace

extern "C" {

int cocoa_is_main_thread(void) {
  // There is no AppKit/main-thread affinity in the PS5 fullscreen frontend.
  return 1;
}

int cocoa_active(void) { return g_window_count.load() > 0 ? 1 : 0; }

void cocoa_pump(int wait_ms) {
  {
    std::lock_guard<std::mutex> lock(g_pad_mu);
    if (EnsurePadLocked()) (void)PollDinputPad(&g_pad);
  }
  if (wait_ms > 0) {
    timespec ts{};
    ts.tv_sec = wait_ms / 1000;
    ts.tv_nsec = static_cast<long>(wait_ms % 1000) * 1000000L;
    (void)nanosleep(&ts, nullptr);
  }
}

void* cocoa_window_new(std::uint64_t hwnd, int x, int y, int cw, int ch,
                       int titled, int resizable, int minimizable,
                       const char* title) {
  auto* w = new (std::nothrow) LogicalWindow{};
  if (!w) return nullptr;
  w->hwnd = hwnd;
  w->x = x;
  w->y = y;
  w->w = std::max(1, cw);
  w->h = std::max(1, ch);
  w->titled = titled != 0;
  w->resizable = resizable != 0;
  w->minimizable = minimizable != 0;
  CopyTitle(w, title);
  rt_last_surface_hwnd = hwnd;
  g_cursor_x.store(w->x + w->w / 2);
  g_cursor_y.store(w->y + w->h / 2);
  g_window_count.fetch_add(1);
  return w;
}

void cocoa_window_free(void* p) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (!w) return;
  if (rt_last_surface_hwnd == w->hwnd) rt_last_surface_hwnd = 0;
  delete w;
  g_window_count.fetch_sub(1);
}

void cocoa_window_show(void* p, int show, int activate) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (!w) return;
  w->visible = show != 0;
  if (activate && show) {
    w->minimized = false;
    rt_last_surface_hwnd = w->hwnd;
  }
}

void cocoa_window_minimize(void* p, int minimize) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (w) w->minimized = minimize != 0;
}

void cocoa_window_zoom(void* p, int zoom) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (w) w->zoomed = zoom != 0;
}

void cocoa_window_state(void* p, int* minimized, int* zoomed, int* visible) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (minimized) *minimized = w && w->minimized ? 1 : 0;
  if (zoomed) *zoomed = w && w->zoomed ? 1 : 0;
  if (visible) *visible = w && w->visible ? 1 : 0;
}

void cocoa_window_set_style(void* p, int titled, int resizable,
                            int minimizable) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (!w) return;
  w->titled = titled != 0;
  w->resizable = resizable != 0;
  w->minimizable = minimizable != 0;
}

void cocoa_window_set_client(void* p, int x, int y, int cw, int ch) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (!w) return;
  w->x = x;
  w->y = y;
  w->w = std::max(1, cw);
  w->h = std::max(1, ch);
}

void cocoa_window_get_client(void* p, int* x, int* y, int* cw, int* ch) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (x) *x = w ? w->x : 0;
  if (y) *y = w ? w->y : 0;
  if (cw) *cw = w ? w->w : 0;
  if (ch) *ch = w ? w->h : 0;
}

void cocoa_window_set_title(void* p, const char* title) {
  CopyTitle(static_cast<LogicalWindow*>(p), title);
}

void cocoa_window_activate(void* p) {
  auto* w = static_cast<LogicalWindow*>(p);
  if (!w) return;
  w->visible = true;
  w->minimized = false;
  rt_last_surface_hwnd = w->hwnd;
}

void* cocoa_window_layer(void*) {
  // Metal layer is only required by the excluded macOS Vulkan surface route.
  return nullptr;
}

void cocoa_frame_insets(int, int, int* l, int* t, int* r, int* b) {
  if (l) *l = 0;
  if (t) *t = 0;
  if (r) *r = 0;
  if (b) *b = 0;
}

void cocoa_cursor_pos(int* x, int* y) {
  if (x) *x = g_cursor_x.load();
  if (y) *y = g_cursor_y.load();
}

void cocoa_set_cursor_pos(int x, int y) {
  g_cursor_x.store(x);
  g_cursor_y.store(y);
}

void cocoa_cursor_visible(int visible) {
  g_cursor_visible.store(visible != 0);
}

void cocoa_mouse_delta(int* dx, int* dy) {
  // Relative DualSense motion is injected directly through DirectInput.
  if (dx) *dx = 0;
  if (dy) *dy = 0;
}

void cocoa_set_virtual_screen(int, int) {
  // PS5 display mode selection is handled by the patched display.c hooks.
}

char* cocoa_choose_folder(const char*) {
  // Registered titles cannot present an AppKit-style folder picker.
  return nullptr;
}

void cocoa_alert(const char* title, const char* text) {
  rt_log("[ps5/frontend] alert: %s: %s\n",
         title ? title : "reFrozen", text ? text : "");
}

void cocoa_pick_friends(int, const char* const*, const char* const*,
                        void (*done)(const int*, int, void*), void* context) {
  if (done) done(nullptr, 0, context);
}

void gamepad_start(void) {
  std::lock_guard<std::mutex> lock(g_pad_mu);
  (void)EnsurePadLocked();
}

int gamepad_state(int user, std::uint8_t out[16], int) {
  if (user != 0 || !out) return 0;
  std::lock_guard<std::mutex> lock(g_pad_mu);
  Data sample{};
  if (!ReadPadLocked(&sample)) return 0;

  std::uint8_t state[12]{};
  const std::uint16_t buttons = XInputButtons(sample.buttons);
  std::memcpy(state, &buttons, sizeof(buttons));
  state[2] = sample.triggers.l2;
  state[3] = sample.triggers.r2;
  const std::int16_t axes[4] = {
      Axis(sample.left_stick.x, false),
      Axis(sample.left_stick.y, true),
      Axis(sample.right_stick.x, false),
      Axis(sample.right_stick.y, true),
  };
  std::memcpy(state + 4, axes, sizeof(axes));
  if (std::memcmp(state, g_last_xinput, sizeof(state)) != 0) {
    std::memcpy(g_last_xinput, state, sizeof(state));
    ++g_xinput_packet;
    if (!g_xinput_packet) ++g_xinput_packet;
  }
  std::memcpy(out, &g_xinput_packet, sizeof(g_xinput_packet));
  std::memcpy(out + 4, state, sizeof(state));
  return 1;
}

int gamepad_connected(int user) {
  if (user != 0) return 0;
  std::lock_guard<std::mutex> lock(g_pad_mu);
  Data sample{};
  return ReadPadLocked(&sample) ? 1 : 0;
}

int gamepad_rumble(int user, std::uint16_t, std::uint16_t) {
  // First-launch bridge keeps XInput semantics but does not claim haptics
  // until a public scePad vibration contract is independently verified.
  return gamepad_connected(user);
}

void gamepad_battery(int user, std::uint8_t* type, std::uint8_t* level) {
  if (type) *type = gamepad_connected(user) ? 1 : 0;   // wired / disconnected
  if (level) *level = 3;                               // full/unknown
}

}  // extern "C"
