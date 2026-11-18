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

// PE SizeOfImage may be 4 KiB-aligned. This helper rounds the logical image
// size to the native PS5 granule before reserving the exact guest base.
[[nodiscard]] ExactReserveResult ReserveExactGuestImagePs5(
    std::uint64_t base, std::uint64_t logical_size,
    std::uint64_t alignment = kPs5KernelGranule);

}  // namespace refrozen::ps5
