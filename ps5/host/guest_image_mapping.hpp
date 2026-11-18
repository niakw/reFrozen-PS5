// SPDX-License-Identifier: GPL-3.0-or-later
// Composes exact VA reservation and direct backing without owning OS APIs.
#pragma once

#include <cstddef>
#include <cstdint>

#include "direct_guest_backing.hpp"
#include "exact_guest_reservation.hpp"

namespace refrozen::ps5 {

enum class GuestImageMapStatus {
  ok,
  reservation_failed,
  reservation_ownership_ambiguous,
  backing_failed_reservation_released,
  backing_failed_reservation_release_failed,
  backing_ownership_ambiguous,
};

struct GuestImageMapping {
  GuestImageMapStatus status{GuestImageMapStatus::reservation_failed};
  ExactReserveResult reservation{};
  DirectGuestBacking backing{};
  int reservation_cleanup_code{};

  [[nodiscard]] constexpr bool ok() const noexcept {
    return status == GuestImageMapStatus::ok;
  }

  [[nodiscard]] constexpr bool requires_process_abort() const noexcept {
    return status == GuestImageMapStatus::reservation_ownership_ambiguous ||
           status == GuestImageMapStatus::backing_ownership_ambiguous ||
           status == GuestImageMapStatus::backing_failed_reservation_release_failed;
  }
};

[[nodiscard]] constexpr bool ExactReservationOwnershipAmbiguous(
    ExactReserveStatus status) noexcept {
  return status == ExactReserveStatus::reserve_failed_mutated_address ||
         status == ExactReserveStatus::moved_address_release_failed;
}

template <class ReserveImageFn, class BackImageFn, class UnmapFn>
[[nodiscard]] GuestImageMapping MapGuestImage(
    std::uint64_t base, std::uint64_t logical_size, std::uint64_t alignment,
    ReserveImageFn&& reserve_image, BackImageFn&& back_image,
    UnmapFn&& unmap_reservation) {
  GuestImageMapping out{};
  out.reservation = reserve_image(base, logical_size, alignment);
  if (!out.reservation.ok()) {
    out.status = ExactReservationOwnershipAmbiguous(out.reservation.status)
                     ? GuestImageMapStatus::reservation_ownership_ambiguous
                     : GuestImageMapStatus::reservation_failed;
    return out;
  }

  out.backing = back_image(base, logical_size, alignment);
  if (out.backing.ok()) {
    out.status = GuestImageMapStatus::ok;
    return out;
  }

  // A failed native map that changed its output address, or a successful
  // wrong-address map whose alias could not be removed, has uncertain VA
  // ownership. Do not touch the original reservation: terminate the process.
  if (out.backing.ownership_ambiguous()) {
    out.status = GuestImageMapStatus::backing_ownership_ambiguous;
    return out;
  }

  // All other backing failures leave the exact reservation at the requested
  // address. Release it so a failed game launch does not leak VA space.
  if (!out.reservation.requested || !out.reservation.size) {
    out.status = GuestImageMapStatus::backing_failed_reservation_release_failed;
    out.reservation_cleanup_code = -1;
    return out;
  }
  out.reservation_cleanup_code = unmap_reservation(
      reinterpret_cast<void*>(out.reservation.requested),
      out.reservation.size);
  out.status = out.reservation_cleanup_code == 0
                   ? GuestImageMapStatus::backing_failed_reservation_released
                   : GuestImageMapStatus::backing_failed_reservation_release_failed;
  return out;
}

}  // namespace refrozen::ps5
