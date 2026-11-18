// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_image_mapping_ps5.hpp"

#include "direct_guest_backing_ps5.hpp"
#include "exact_reservation_ps5.hpp"

#include <cstddef>
#include <sys/mman.h>

namespace refrozen::ps5 {

GuestImageMapping MapGuestImagePs5(
    std::uint64_t base, std::uint64_t logical_size,
    std::uint64_t alignment) {
  return MapGuestImage(
      base, logical_size, alignment,
      [](std::uint64_t image_base, std::uint64_t image_size,
         std::uint64_t image_alignment) {
        return ReserveExactGuestImagePs5(
            image_base, image_size, image_alignment);
      },
      [](std::uint64_t image_base, std::uint64_t image_size,
         std::uint64_t image_alignment) {
        return MapDirectGuestBackingPs5(
            image_base, image_size, image_alignment);
      },
      [](void* address, std::size_t bytes) {
        return munmap(address, bytes);
      });
}

DirectBackingReleaseResult ReleaseGuestImagePs5(
    const GuestImageMapping& mapping) {
  if (!mapping.ok()) return {};
  return ReleaseDirectGuestBackingPs5(mapping.backing);
}

}  // namespace refrozen::ps5
