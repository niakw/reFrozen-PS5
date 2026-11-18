// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

#include "guest_image_mapping.hpp"

namespace refrozen::ps5 {

[[nodiscard]] GuestImageMapping MapGuestImagePs5(
    std::uint64_t base, std::uint64_t logical_size,
    std::uint64_t alignment = kPs5KernelGranule);

[[nodiscard]] DirectBackingReleaseResult ReleaseGuestImagePs5(
    const GuestImageMapping& mapping);

}  // namespace refrozen::ps5
