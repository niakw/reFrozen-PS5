// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_image_mapping.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>

using namespace refrozen::ps5;

namespace {
constexpr std::uint64_t kBase = 0x140000000ULL;
constexpr std::uint64_t kLogical = 0x5000;
constexpr std::uint64_t kMapped = 0x8000;

ExactReserveResult Reservation(ExactReserveStatus status) {
  ExactReserveResult r{};
  r.status = status;
  r.requested = kBase;
  r.observed = kBase;
  r.size = status == ExactReserveStatus::ok ? kMapped : 0;
  return r;
}

DirectGuestBacking Backing(DirectBackingStatus status) {
  DirectGuestBacking b{};
  b.status = status;
  b.address = kBase;
  b.logical_size = kLogical;
  b.mapped_size = kMapped;
  b.physical = status == DirectBackingStatus::ok ? 0x200000 : -1;
  if (status == DirectBackingStatus::map_failed_mutated_address ||
      status == DirectBackingStatus::wrong_address_unmap_failed) {
    b.address = 0x150000000ULL;
    b.physical = 0x200000;
  }
  return b;
}
}  // namespace

int main() {
  {
    int reserves = 0, backs = 0, unmaps = 0;
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t base, std::uint64_t logical, std::uint64_t alignment) {
          ++reserves;
          assert(base == kBase && logical == kLogical &&
                 alignment == kPs5KernelGranule);
          return Reservation(ExactReserveStatus::ok);
        },
        [&](std::uint64_t base, std::uint64_t logical, std::uint64_t alignment) {
          ++backs;
          assert(base == kBase && logical == kLogical &&
                 alignment == kPs5KernelGranule);
          return Backing(DirectBackingStatus::ok);
        },
        [&](void*, std::size_t) {
          ++unmaps;
          return 0;
        });
    assert(r.ok());
    assert(reserves == 1 && backs == 1 && unmaps == 0);
  }
  {
    int backs = 0, unmaps = 0;
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Reservation(ExactReserveStatus::reserve_failed);
        },
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          ++backs;
          return Backing(DirectBackingStatus::ok);
        },
        [&](void*, std::size_t) {
          ++unmaps;
          return 0;
        });
    assert(r.status == GuestImageMapStatus::reservation_failed);
    assert(!r.requires_process_abort());
    assert(backs == 0 && unmaps == 0);
  }
  for (const auto ambiguous : {
           ExactReserveStatus::reserve_failed_mutated_address,
           ExactReserveStatus::moved_address_release_failed}) {
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Reservation(ambiguous);
        },
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          assert(false && "backing must not run after ambiguous reservation");
          return Backing(DirectBackingStatus::ok);
        },
        [&](void*, std::size_t) {
          assert(false && "cleanup must not guess ownership");
          return 0;
        });
    assert(r.status == GuestImageMapStatus::reservation_ownership_ambiguous);
    assert(r.requires_process_abort());
  }
  {
    int unmaps = 0;
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Reservation(ExactReserveStatus::ok);
        },
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Backing(DirectBackingStatus::allocate_failed);
        },
        [&](void* address, std::size_t size) {
          ++unmaps;
          assert(address == reinterpret_cast<void*>(kBase));
          assert(size == kMapped);
          return 0;
        });
    assert(r.status == GuestImageMapStatus::backing_failed_reservation_released);
    assert(!r.requires_process_abort());
    assert(unmaps == 1);
  }
  {
    int unmaps = 0;
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Reservation(ExactReserveStatus::ok);
        },
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Backing(DirectBackingStatus::map_failed_mutated_address);
        },
        [&](void*, std::size_t) {
          ++unmaps;
          return 0;
        });
    assert(r.status == GuestImageMapStatus::backing_ownership_ambiguous);
    assert(r.requires_process_abort());
    assert(unmaps == 0);
  }
  {
    const auto r = MapGuestImage(
        kBase, kLogical, kPs5KernelGranule,
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Reservation(ExactReserveStatus::ok);
        },
        [&](std::uint64_t, std::uint64_t, std::uint64_t) {
          return Backing(DirectBackingStatus::map_failed_physical_released);
        },
        [&](void* address, std::size_t size) {
          assert(address == reinterpret_cast<void*>(kBase));
          assert(size == kMapped);
          return -9;
        });
    assert(r.status ==
           GuestImageMapStatus::backing_failed_reservation_release_failed);
    assert(r.requires_process_abort());
    assert(r.reservation_cleanup_code == -9);
  }

  std::cout << "guest_image_mapping: PASS\n";
}
