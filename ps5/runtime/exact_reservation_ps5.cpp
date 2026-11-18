// SPDX-License-Identifier: GPL-3.0-or-later
#include "exact_reservation_ps5.hpp"

#include <cstddef>
#include <cstdint>
#include <sys/mman.h>

extern "C" {
std::int32_t sceKernelReserveVirtualRange(void**, std::size_t, int, std::size_t);
}

namespace refrozen::ps5 {

ExactReserveResult ReserveExactGuestRangePs5(
    std::uint64_t base, std::uint64_t size, std::uint64_t alignment) {
  return ReserveExactGuestRange(
      base, size, alignment,
      [](void** address, std::size_t bytes, int flags, std::size_t align) {
        return static_cast<int>(
            sceKernelReserveVirtualRange(address, bytes, flags, align));
      },
      [](void* address, std::size_t bytes) {
        return munmap(address, bytes);
      });
}

ExactReserveResult ReserveExactGuestImagePs5(
    std::uint64_t base, std::uint64_t logical_size,
    std::uint64_t alignment) {
  const auto mapped_size = RoundGuestMappingSize(logical_size, alignment);
  if (!mapped_size) {
    ExactReserveResult invalid{};
    invalid.requested = static_cast<std::uintptr_t>(base);
    invalid.status = ExactReserveStatus::invalid_arguments;
    return invalid;
  }
  return ReserveExactGuestRangePs5(base, mapped_size, alignment);
}

}  // namespace refrozen::ps5
