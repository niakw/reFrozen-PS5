// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_dinput_pad_bridge.hpp"
#include "ps5_pad_contract.hpp"

#include <cmath>
#include <cstdint>

extern "C" {
void di_key(std::uint32_t scan, int ext, int down);
void di_mouse_move(int dx, int dy);
void di_mouse_wheel(int dz);
void di_mouse_button(int button, int down);
}

namespace refrozen::ps5 {
namespace {
using namespace refrozen::ps5::pad;

constexpr float kDeadzone = 0.12f;
constexpr float kMousePixelsPerPoll = 18.0f;
constexpr int kWheelDelta = 120;

// Set-1 scan codes. DirectInput adds 0x80 when ext != 0.
constexpr std::uint32_t kScanEscape = 0x01;
constexpr std::uint32_t kScanUp = 0x48;
constexpr std::uint32_t kScanRight = 0x4d;
constexpr std::uint32_t kScanDown = 0x50;
constexpr std::uint32_t kScanLeft = 0x4b;

float Axis(std::uint8_t raw) {
  const float value =
      raw < 128 ? (static_cast<int>(raw) - 128) / 128.0f
                : (static_cast<int>(raw) - 128) / 127.0f;
  const float magnitude = std::fabs(value);
  if (magnitude <= kDeadzone) return 0.0f;
  const float scaled = (magnitude - kDeadzone) / (1.0f - kDeadzone);
  return std::copysign(scaled, value);
}

bool Down(std::uint32_t buttons, std::uint32_t mask) {
  return (buttons & mask) != 0;
}

void EdgeButton(std::uint32_t now, std::uint32_t before, std::uint32_t mask,
                int mouse_button) {
  const bool current = Down(now, mask);
  if (current != Down(before, mask))
    di_mouse_button(mouse_button, current ? 1 : 0);
}

void EdgeKey(std::uint32_t now, std::uint32_t before, std::uint32_t mask,
             std::uint32_t scan, bool extended) {
  const bool current = Down(now, mask);
  if (current != Down(before, mask))
    di_key(scan, extended ? 1 : 0, current ? 1 : 0);
}

int Quantize(float movement, float* remainder) {
  const float accumulated = movement + *remainder;
  const int whole = static_cast<int>(std::trunc(accumulated));
  *remainder = accumulated - static_cast<float>(whole);
  return whole;
}

void ReleaseHeld(std::uint32_t buttons) {
  if (Down(buttons, kButtonCross)) di_mouse_button(0, 0);
  if (Down(buttons, kButtonCircle)) di_mouse_button(1, 0);
  if (Down(buttons, kButtonOptions)) di_key(kScanEscape, 0, 0);
  if (Down(buttons, kButtonUp)) di_key(kScanUp, 1, 0);
  if (Down(buttons, kButtonRight)) di_key(kScanRight, 1, 0);
  if (Down(buttons, kButtonDown)) di_key(kScanDown, 1, 0);
  if (Down(buttons, kButtonLeft)) di_key(kScanLeft, 1, 0);
}

}  // namespace

int OpenDinputPad(DinputPadBridge* bridge) {
  if (!bridge) return -1;
  if (bridge->handle >= 0) return 0;

  bridge->owns_user_service = sceUserServiceInitialize(nullptr) == 0;
  int user = -1;
  if (sceUserServiceGetForegroundUser(&user) < 0 || user < 0 ||
      scePadInit() < 0) {
    CloseDinputPad(bridge);
    return -1;
  }
  const int handle = scePadOpen(user, kPortTypeStandard, 0, nullptr);
  if (handle < 0) {
    CloseDinputPad(bridge);
    return handle;
  }
  bridge->handle = handle;
  bridge->last_buttons = 0;
  bridge->remainder_x = 0.0f;
  bridge->remainder_y = 0.0f;
  return 0;
}

int PollDinputPad(DinputPadBridge* bridge) {
  if (!bridge || bridge->handle < 0) return -1;

  Data sample{};
  const int result = scePadReadState(bridge->handle, &sample);
  if (result < 0) return result;
  if (!usable(sample)) return 0;

  const std::uint32_t now = sample.buttons;
  const std::uint32_t before = bridge->last_buttons;

  const int dx = Quantize(Axis(sample.right_stick.x) * kMousePixelsPerPoll,
                          &bridge->remainder_x);
  const int dy = Quantize(Axis(sample.right_stick.y) * kMousePixelsPerPoll,
                          &bridge->remainder_y);
  if (dx || dy) di_mouse_move(dx, dy);

  EdgeButton(now, before, kButtonCross, 0);
  EdgeButton(now, before, kButtonCircle, 1);
  EdgeKey(now, before, kButtonOptions, kScanEscape, false);
  EdgeKey(now, before, kButtonUp, kScanUp, true);
  EdgeKey(now, before, kButtonRight, kScanRight, true);
  EdgeKey(now, before, kButtonDown, kScanDown, true);
  EdgeKey(now, before, kButtonLeft, kScanLeft, true);

  // Wheel only on the rising edge so holding a shoulder does not scroll at
  // the 250 Hz pad polling rate.
  if (Down(now, kButtonL1) && !Down(before, kButtonL1))
    di_mouse_wheel(kWheelDelta);
  if (Down(now, kButtonR1) && !Down(before, kButtonR1))
    di_mouse_wheel(-kWheelDelta);

  bridge->last_buttons = now;
  return 1;
}

void CloseDinputPad(DinputPadBridge* bridge) {
  if (!bridge) return;
  ReleaseHeld(bridge->last_buttons);
  bridge->last_buttons = 0;
  bridge->remainder_x = bridge->remainder_y = 0.0f;
  if (bridge->handle >= 0) {
    (void)scePadClose(bridge->handle);
    bridge->handle = -1;
  }
  if (bridge->owns_user_service) {
    (void)sceUserServiceTerminate();
    bridge->owns_user_service = false;
  }
}

}  // namespace refrozen::ps5
