// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_pad_contract.hpp"

#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

using refrozen::ps5::pad::Data;

namespace {
Data sample{};
int user_init_calls;
int user_term_calls;
int pad_open_calls;
int pad_close_calls;
int graphics_init_calls;
}

extern "C" {
int cocoa_active(void);
void* cocoa_window_new(std::uint64_t hwnd, int x, int y, int cw, int ch,
                       int titled, int resizable, int minimizable,
                       const char* title);
void cocoa_window_free(void*);
void cocoa_window_show(void*, int show, int activate);
void cocoa_window_minimize(void*, int);
void cocoa_window_zoom(void*, int);
void cocoa_window_state(void*, int*, int*, int*);
void cocoa_window_set_client(void*, int, int, int, int);
void cocoa_window_get_client(void*, int*, int*, int*, int*);
void cocoa_cursor_pos(int*, int*);
void cocoa_set_cursor_pos(int, int);
void cocoa_frame_insets(int, int, int*, int*, int*, int*);
int gamepad_state(int user, std::uint8_t out[16], int guide);
int gamepad_connected(int user);
int gamepad_rumble(int user, std::uint16_t left, std::uint16_t right);
void gamepad_battery(int user, std::uint8_t* type, std::uint8_t* level);
extern std::uint64_t rt_last_surface_hwnd;
int rt_ps5_frontend_init(void);

void rt_log(const char*, ...) {}
int rt_ps5_graphics_init(void) { ++graphics_init_calls; return 0; }

std::int32_t sceUserServiceInitialize(void*) {
  ++user_init_calls;
  return 0;
}
std::int32_t sceUserServiceGetForegroundUser(std::int32_t* user) {
  *user = 77;
  return 0;
}
std::int32_t sceUserServiceTerminate() {
  ++user_term_calls;
  return 0;
}
std::int32_t scePadInit() { return 0; }
std::int32_t scePadOpen(std::int32_t user, std::int32_t type,
                        std::int32_t index, const void*) {
  assert(user == 77 && type == 0 && index == 0);
  ++pad_open_calls;
  return 12;
}
std::int32_t scePadClose(std::int32_t handle) {
  assert(handle == 12);
  ++pad_close_calls;
  return 0;
}
std::int32_t scePadReadState(std::int32_t handle, Data* out) {
  assert(handle == 12);
  *out = sample;
  return 0;
}

// DirectInput feeds required by ps5_dinput_pad_bridge.cpp.
void di_key(std::uint32_t, int, int) {}
void di_mouse_move(int, int) {}
void di_mouse_wheel(int) {}
void di_mouse_button(int, int) {}
}

int main() {
  assert(rt_ps5_frontend_init() == 0);
  assert(graphics_init_calls == 1);
  assert(user_init_calls == 1 && pad_open_calls == 1);

  assert(cocoa_active() == 0);
  void* window = cocoa_window_new(
      0x1234, 10, 20, 1280, 720, 0, 0, 0, "Warcraft");
  assert(window && cocoa_active() == 1);
  assert(rt_last_surface_hwnd == 0x1234);

  cocoa_window_show(window, 1, 1);
  int minimized = -1, zoomed = -1, visible = -1;
  cocoa_window_state(window, &minimized, &zoomed, &visible);
  assert(minimized == 0 && visible == 1);

  cocoa_window_minimize(window, 1);
  cocoa_window_zoom(window, 0);
  cocoa_window_state(window, &minimized, &zoomed, &visible);
  assert(minimized == 1 && zoomed == 0);

  cocoa_window_set_client(window, 30, 40, 1920, 1080);
  int x = 0, y = 0, w = 0, h = 0;
  cocoa_window_get_client(window, &x, &y, &w, &h);
  assert(x == 30 && y == 40 && w == 1920 && h == 1080);

  cocoa_set_cursor_pos(321, 654);
  cocoa_cursor_pos(&x, &y);
  assert(x == 321 && y == 654);
  int l = -1, t = -1, r = -1, b = -1;
  cocoa_frame_insets(1, 1, &l, &t, &r, &b);
  assert(l == 0 && t == 0 && r == 0 && b == 0);

  using namespace refrozen::ps5::pad;
  sample = {};
  sample.connected = 1;
  sample.left_stick = {255, 0};
  sample.right_stick = {128, 128};
  sample.triggers.l2 = 64;
  sample.triggers.r2 = 192;
  sample.buttons = kButtonCross | kButtonCircle | kButtonOptions |
                   kButtonTouchPad | kButtonUp | kButtonL1 | kButtonR3;

  std::uint8_t state[16]{};
  assert(gamepad_state(0, state, 1) == 1);
  assert(gamepad_connected(0) == 1);
  assert(gamepad_connected(1) == 0);
  std::uint16_t buttons = 0;
  std::memcpy(&buttons, state + 4, sizeof(buttons));
  assert((buttons & 0x1000) != 0);  // A / Cross
  assert((buttons & 0x2000) != 0);  // B / Circle
  assert((buttons & 0x0010) != 0);  // Start / Options
  assert((buttons & 0x0020) != 0);  // Back / touchpad
  assert((buttons & 0x0001) != 0);  // D-pad up
  assert((buttons & 0x0100) != 0);  // L shoulder
  assert((buttons & 0x0080) != 0);  // R thumb
  assert(state[6] == 64 && state[7] == 192);
  std::int16_t axes[4]{};
  std::memcpy(axes, state + 8, sizeof(axes));
  assert(axes[0] > 32000);
  assert(axes[1] > 32000);  // raw Y=0 means up => positive XInput Y.

  std::uint32_t first_packet = 0;
  std::memcpy(&first_packet, state, sizeof(first_packet));
  assert(gamepad_state(0, state, 1) == 1);
  std::uint32_t second_packet = 0;
  std::memcpy(&second_packet, state, sizeof(second_packet));
  assert(second_packet == first_packet);

  sample.buttons ^= kButtonSquare;
  assert(gamepad_state(0, state, 1) == 1);
  std::uint32_t changed_packet = 0;
  std::memcpy(&changed_packet, state, sizeof(changed_packet));
  assert(changed_packet != first_packet);

  std::uint8_t battery_type = 0, battery_level = 0;
  gamepad_battery(0, &battery_type, &battery_level);
  assert(battery_type == 1 && battery_level == 3);
  assert(gamepad_rumble(0, 0xffff, 0xffff) == 1);

  cocoa_window_free(window);
  assert(cocoa_active() == 0 && rt_last_surface_hwnd == 0);
  assert(user_init_calls == 1 && pad_open_calls == 1);

  std::puts("ps5_win64_frontend_shims: PASS");
  return 0;
}
