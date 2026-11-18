// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

namespace refrozen::ps5 {

struct DinputPadBridge {
  int handle{-1};
  bool owns_user_service{false};
  std::uint32_t last_buttons{0};
  float remainder_x{0.0f};
  float remainder_y{0.0f};
};

int OpenDinputPad(DinputPadBridge* bridge);
int PollDinputPad(DinputPadBridge* bridge);
void CloseDinputPad(DinputPadBridge* bridge);

}  // namespace refrozen::ps5
