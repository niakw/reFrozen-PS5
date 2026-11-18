// SPDX-License-Identifier: GPL-3.0-or-later
// Ownership-safe direct-memory backing state machine for an exact guest VA.
// OS calls are injected so every transition can be tested without a PS5 SDK.
#pragma once

#include <cstddef>
#include <cstdint>

#include "exact_guest_reservation.hpp"

namespace refrozen::ps5 {

constexpr int kPs5CpuDirectMemoryType = 12;

enum class DirectBackingStatus {
  ok,
  invalid_arguments,
  extent_unavailable,
  allocate_failed,
  map_failed_physical_released,
  map_failed_release_failed,
  map_failed_mutated_address,
  wrong_address_cleaned,
  wrong_address_unmap_failed,
  wrong_address_release_failed,
};

struct DirectGuestBacking {
  DirectBackingStatus status{DirectBackingStatus::invalid_arguments};
  std::uintptr_t address{};
  std::size_t mapped_size{};
  std::uint64_t logical_size{};
  std::int64_t physical{-1};
  int allocate_code{};
  int map_code{};
  int unmap_code{};
  int release_code{};

  [[nodiscard]] constexpr bool ok() const noexcept {
    return status == DirectBackingStatus::ok;
  }

  [[nodiscard]] constexpr bool ownership_ambiguous() const noexcept {
    return status == DirectBackingStatus::map_failed_mutated_address ||
           status == DirectBackingStatus::wrong_address_unmap_failed;
  }
};

template <class ExtentFn, class AllocateFn, class MapFn,
          class UnmapFn, class ReleaseFn>
[[nodiscard]] DirectGuestBacking MapDirectGuestBacking(
    std::uint64_t address, std::uint64_t logical_size,
    std::uint64_t alignment, int map_protection, int map_flags,
    ExtentFn&& get_extent, AllocateFn&& allocate, MapFn&& map,
    UnmapFn&& unmap, ReleaseFn&& release) {
  DirectGuestBacking out{};
  const auto mapped_size = RoundGuestMappingSize(logical_size, alignment);
  if (!mapped_size || address > UINTPTR_MAX ||
      (address & (alignment - 1)) != 0 ||
      mapped_size > SIZE_MAX ||
      CheckEncoreGuestVaPolicy(address, mapped_size) != GuestVaPolicy::allowed) {
    return out;
  }
  out.address = static_cast<std::uintptr_t>(address);
  out.logical_size = logical_size;
  out.mapped_size = static_cast<std::size_t>(mapped_size);

  const std::int64_t extent = get_extent();
  if (extent <= 0) {
    out.status = DirectBackingStatus::extent_unavailable;
    return out;
  }

  out.allocate_code = allocate(
      std::int64_t{0}, extent, out.mapped_size,
      static_cast<std::size_t>(alignment), kPs5CpuDirectMemoryType,
      &out.physical);
  if (out.allocate_code != 0 || out.physical < 0) {
    out.status = DirectBackingStatus::allocate_failed;
    return out;
  }

  void* requested = reinterpret_cast<void*>(out.address);
  void* observed = requested;
  out.map_code = map(&observed, out.mapped_size, map_protection, map_flags,
                     out.physical, static_cast<std::size_t>(alignment));

  if (out.map_code != 0) {
    if (observed != requested) {
      // Like Encore's native allocator, do not guess alias ownership after a
      // failing syscall mutates the output VA. Caller should terminate.
      out.address = reinterpret_cast<std::uintptr_t>(observed);
      out.status = DirectBackingStatus::map_failed_mutated_address;
      return out;
    }
    out.release_code = release(out.physical, out.mapped_size);
    out.status = out.release_code == 0
                     ? DirectBackingStatus::map_failed_physical_released
                     : DirectBackingStatus::map_failed_release_failed;
    if (out.release_code == 0) out.physical = -1;
    return out;
  }

  if (observed != requested) {
    out.address = reinterpret_cast<std::uintptr_t>(observed);
    out.unmap_code = unmap(observed, out.mapped_size);
    if (out.unmap_code != 0) {
      out.status = DirectBackingStatus::wrong_address_unmap_failed;
      return out;
    }
    out.release_code = release(out.physical, out.mapped_size);
    if (out.release_code != 0) {
      out.status = DirectBackingStatus::wrong_address_release_failed;
      return out;
    }
    out.physical = -1;
    out.status = DirectBackingStatus::wrong_address_cleaned;
    return out;
  }

  out.status = DirectBackingStatus::ok;
  return out;
}

enum class DirectBackingReleaseStatus {
  ok,
  invalid,
  unmap_failed,
  physical_release_failed,
};

struct DirectBackingReleaseResult {
  DirectBackingReleaseStatus status{DirectBackingReleaseStatus::invalid};
  int unmap_code{};
  int release_code{};
};

template <class UnmapFn, class ReleaseFn>
[[nodiscard]] DirectBackingReleaseResult ReleaseDirectGuestBacking(
    const DirectGuestBacking& backing, UnmapFn&& unmap, ReleaseFn&& release) {
  DirectBackingReleaseResult out{};
  if (!backing.ok() || backing.physical < 0 || !backing.address ||
      !backing.mapped_size) {
    return out;
  }
  out.unmap_code = unmap(reinterpret_cast<void*>(backing.address),
                         backing.mapped_size);
  if (out.unmap_code != 0) {
    out.status = DirectBackingReleaseStatus::unmap_failed;
    return out;  // never free physical memory while an alias may still exist
  }
  out.release_code = release(backing.physical, backing.mapped_size);
  out.status = out.release_code == 0
                   ? DirectBackingReleaseStatus::ok
                   : DirectBackingReleaseStatus::physical_release_failed;
  return out;
}

}  // namespace refrozen::ps5
