// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_dinput_pad_bridge.hpp"
#include "ps5_pad_contract.hpp"

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>

namespace {
using refrozen::ps5::pad::Data;
Data next_sample{};
int init_calls;
int term_calls;
int open_calls;
int close_calls;
struct KeyEvent { std::uint32_t scan; int ext; int down; };
struct ButtonEvent { int button; int down; };
std::vector<KeyEvent> keys;
std::vector<ButtonEvent> buttons;
std::vector<int> wheels;
std::vector<std::pair<int,int>> moves;
}

extern "C" {
std::int32_t sceUserServiceInitialize(void*) { ++init_calls; return 0; }
std::int32_t sceUserServiceGetForegroundUser(std::int32_t* user) {
  *user = 42; return 0;
}
std::int32_t sceUserServiceTerminate() { ++term_calls; return 0; }
std::int32_t scePadInit() { return 0; }
std::int32_t scePadOpen(std::int32_t user, std::int32_t type,
                        std::int32_t index, const void*) {
  assert(user == 42 && type == 0 && index == 0);
  ++open_calls; return 9;
}
std::int32_t scePadClose(std::int32_t handle) {
  assert(handle == 9); ++close_calls; return 0;
}
std::int32_t scePadReadState(std::int32_t handle, Data* out) {
  assert(handle == 9); *out = next_sample; return 0;
}

void di_key(std::uint32_t scan, int ext, int down) {
  keys.push_back({scan, ext, down});
}
void di_mouse_move(int dx, int dy) { moves.emplace_back(dx, dy); }
void di_mouse_wheel(int dz) { wheels.push_back(dz); }
void di_mouse_button(int button, int down) {
  buttons.push_back({button, down});
}
}

int main() {
  using namespace refrozen::ps5;
  using namespace refrozen::ps5::pad;

  DinputPadBridge bridge{};
  assert(OpenDinputPad(&bridge) == 0);
  assert(bridge.handle == 9 && bridge.owns_user_service);
  assert(init_calls == 1 && open_calls == 1);

  next_sample = {};
  next_sample.connected = 1;
  next_sample.left_stick = {128, 128};
  next_sample.right_stick = {255, 128};
  next_sample.buttons =
      kButtonCross | kButtonOptions | kButtonUp | kButtonL1;
  assert(PollDinputPad(&bridge) == 1);
  assert(moves.size() == 1 && moves[0].first > 0 && moves[0].second == 0);
  assert(buttons.size() == 1 && buttons[0].button == 0 && buttons[0].down == 1);
  assert(wheels.size() == 1 && wheels[0] == 120);
  assert(keys.size() == 2);
  assert(keys[0].scan == 0x01 && keys[0].ext == 0 && keys[0].down == 1);
  assert(keys[1].scan == 0x48 && keys[1].ext == 1 && keys[1].down == 1);

  // Held digital inputs do not repeat; analog mouse movement does.
  assert(PollDinputPad(&bridge) == 1);
  assert(moves.size() == 2);
  assert(buttons.size() == 1);
  assert(wheels.size() == 1);
  assert(keys.size() == 2);

  // Release all held inputs. Should emit releases but not wheel release.
  next_sample.buttons = 0;
  next_sample.right_stick = {128, 128};
  assert(PollDinputPad(&bridge) == 1);
  assert(buttons.size() == 2 && buttons.back().down == 0);
  assert(keys.size() == 4);
  assert(keys[2].scan == 0x01 && keys[2].down == 0);
  assert(keys[3].scan == 0x48 && keys[3].down == 0);

  // Intercepted samples are ignored without changing edge state.
  next_sample.buttons = kButtonCircle | kButtonIntercepted;
  assert(PollDinputPad(&bridge) == 0);
  assert(buttons.size() == 2);
  next_sample.buttons = kButtonCircle;
  assert(PollDinputPad(&bridge) == 1);
  assert(buttons.size() == 3 && buttons.back().button == 1 &&
         buttons.back().down == 1);

  // Close releases held buttons and owns the user-service lifecycle.
  CloseDinputPad(&bridge);
  assert(buttons.size() == 4 && buttons.back().button == 1 &&
         buttons.back().down == 0);
  assert(close_calls == 1 && term_calls == 1);
  assert(bridge.handle == -1 && !bridge.owns_user_service);

  std::puts("ps5_dinput_pad_bridge: PASS");
  return 0;
}
