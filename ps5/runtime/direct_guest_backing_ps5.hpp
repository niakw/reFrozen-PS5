// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

#include "direct_guest_backing.hpp"

namespace refrozen::ps5 {

// Requires the logical guest range to have passed exact-VA reservation first.
// Replaces that reservation with non-executable PS5 direct-memory backing.
[[nodiscard]] DirectGuestBacking MapDirectGuestBackingPs5(
    std::uint64_t address, std::uint64_t logical_size,
    std::uint64_t alignment = kPs5KernelGranule);

[[nodiscard]] DirectBackingReleaseResult ReleaseDirectGuestBackingPs5(
    const DirectGuestBacking& backing);

}  // namespace refrozen::ps5
