// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

#include "guest_image_mapping_ps5.hpp"

namespace refrozen::ps5 {

enum class GuestMemoryProbeStatus {
  ok,
  mapping_failed,
  ownership_ambiguous,
  marker_mismatch,
  release_failed,
};

struct GuestMemoryProbeResult {
  GuestMemoryProbeStatus status{GuestMemoryProbeStatus::mapping_failed};
  GuestImageMapping mapping{};
  DirectBackingReleaseResult release{};
  std::uint64_t marker_written{};
  std::uint64_t marker_read{};

  [[nodiscard]] constexpr bool ok() const noexcept {
    return status == GuestMemoryProbeStatus::ok;
  }

  [[nodiscard]] constexpr bool requires_process_abort() const noexcept {
    return status == GuestMemoryProbeStatus::ownership_ambiguous ||
           (status == GuestMemoryProbeStatus::release_failed &&
            release.status == DirectBackingReleaseStatus::unmap_failed);
  }
};

// Synthetic only: reserves/maps no Warcraft data. The default logical size is
// intentionally not 16 KiB aligned, exercising 0x5000 -> 0x8000 rounding.
[[nodiscard]] GuestMemoryProbeResult RunSyntheticGuestMemoryProbePs5(
    std::uint64_t base = 0x140000000ULL,
    std::uint64_t logical_size = 0x5000ULL);

}  // namespace refrozen::ps5
