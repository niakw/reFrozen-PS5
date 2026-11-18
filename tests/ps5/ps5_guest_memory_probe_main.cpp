// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_memory_probe_ps5.hpp"

#include <cstdio>

int main() {
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
