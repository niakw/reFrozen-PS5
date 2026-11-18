// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include "exact_guest_reservation.hpp"

namespace refrozen::ps5 {

// Reserves exactly [base, base+size) in the PS5 process. This reserves VA only;
// direct-memory backing/mapping is a separate operation.
[[nodiscard]] ExactReserveResult ReserveExactGuestRangePs5(
    std::uint64_t base, std::uint64_t size,
    std::uint64_t alignment = kPs5KernelGranule);

}  // namespace refrozen::ps5
