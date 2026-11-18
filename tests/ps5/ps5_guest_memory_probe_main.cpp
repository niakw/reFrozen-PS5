// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_memory_probe_ps5.hpp"
#include "win64_memory_bridge_ps5.h"

#include <cstdio>

int main() {
  refrozen_ps5_guest_map_info invalid{};
  if (refrozen_ps5_map_guest_rw(0, 0, 0x4000, &invalid) !=
          REFROZEN_PS5_GUEST_MAP_INVALID ||
      invalid.code != REFROZEN_PS5_GUEST_MAP_INVALID) {
    std::fprintf(stderr, "REFROZEN_PS5_MEMORY_BRIDGE invalid_contract=fail\n");
    return 3;
  }

  const auto result = refrozen::ps5::RunSyntheticGuestMemoryProbePs5();
  if (result.ok()) {
    std::fprintf(stderr, "REFROZEN_PS5_MEMORY_PROBE_MAIN result=pass\n");
    return 0;
  }

  std::fprintf(
      stderr,
      "REFROZEN_PS5_MEMORY_PROBE_MAIN result=fail status=%d abort=%d map=%d release=%d\n",
      static_cast<int>(result.status),
      result.requires_process_abort() ? 1 : 0,
      static_cast<int>(result.mapping.status),
      static_cast<int>(result.release.status));
  return result.requires_process_abort() ? 2 : 1;
}
