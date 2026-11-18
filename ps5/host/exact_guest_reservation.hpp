// SPDX-License-Identifier: GPL-3.0-or-later
// Exact virtual-address reservation contract for Win64 identity-mapped guests.
// Host-independent: callers provide the reserve/release functions.
#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>

namespace refrozen::ps5 {

constexpr std::uint64_t kEncoreRadv32WindowBegin = 0x200000000ULL;
constexpr std::uint64_t kEncoreRadv32WindowEnd = 0x300000000ULL;
constexpr std::uint64_t kEncoreDeviceMemoryBegin = 0x4000000000ULL;
constexpr std::uint64_t kPs5KernelGranule = 0x4000ULL;

enum class GuestVaPolicy {
  allowed,
  invalid,
  overlaps_radv_32_window,
  reaches_device_memory_window,
};

[[nodiscard]] constexpr bool RangeOverlaps(std::uint64_t base, std::uint64_t size,
                                           std::uint64_t other_begin,
                                           std::uint64_t other_end) noexcept {
  if (!size || base > std::numeric_limits<std::uint64_t>::max() - size) return false;
  const auto end = base + size;
  return base < other_end && other_begin < end;
}

// This is an Encore-derived collision policy, not a proof that any allowed
// address is available in the PS5 process. Exact reservation still decides.
[[nodiscard]] constexpr GuestVaPolicy CheckEncoreGuestVaPolicy(
    std::uint64_t base, std::uint64_t size) noexcept {
  if (!size || base > std::numeric_limits<std::uint64_t>::max() - size)
    return GuestVaPolicy::invalid;
  if (RangeOverlaps(base, size, kEncoreRadv32WindowBegin, kEncoreRadv32WindowEnd))
    return GuestVaPolicy::overlaps_radv_32_window;
  if (base + size > kEncoreDeviceMemoryBegin)
    return GuestVaPolicy::reaches_device_memory_window;
  return GuestVaPolicy::allowed;
}

enum class ExactReserveStatus {
  ok,
  invalid_arguments,
  policy_rejected,
  reserve_failed,
  reserve_failed_mutated_address,
  moved_address_released,
  moved_address_release_failed,
};

struct ExactReserveResult {
  ExactReserveStatus status{ExactReserveStatus::invalid_arguments};
  std::uintptr_t requested{};
  std::uintptr_t observed{};
  std::size_t size{};
  int reserve_code{};
  int release_code{};

  [[nodiscard]] constexpr bool ok() const noexcept {
    return status == ExactReserveStatus::ok;
  }
};

template <class ReserveFn, class ReleaseFn>
[[nodiscard]] ExactReserveResult ReserveExactGuestRange(
    std::uint64_t base, std::uint64_t size, std::uint64_t alignment,
    ReserveFn&& reserve, ReleaseFn&& release) {
  ExactReserveResult result{};
  result.requested = static_cast<std::uintptr_t>(base);
  result.observed = result.requested;
  const auto policy = CheckEncoreGuestVaPolicy(base, size);
  if (!size || !alignment || (alignment & (alignment - 1)) != 0 ||
      (base & (alignment - 1)) != 0 || (size & (alignment - 1)) != 0 ||
      size > std::numeric_limits<std::size_t>::max() ||
      base > std::numeric_limits<std::uintptr_t>::max() ||
      policy == GuestVaPolicy::invalid) {
    result.status = ExactReserveStatus::invalid_arguments;
    return result;
  }
  if (policy != GuestVaPolicy::allowed) {
    result.status = ExactReserveStatus::policy_rejected;
    return result;
  }

  result.size = static_cast<std::size_t>(size);
  void* requested = reinterpret_cast<void*>(result.requested);
  void* address = requested;
  result.reserve_code = reserve(&address, result.size, 0,
                                static_cast<std::size_t>(alignment));
  result.observed = reinterpret_cast<std::uintptr_t>(address);

  if (result.reserve_code != 0) {
    result.status = address == requested
                        ? ExactReserveStatus::reserve_failed
                        : ExactReserveStatus::reserve_failed_mutated_address;
    return result;
  }
  if (address != requested) {
    result.release_code = release(address, result.size);
    result.status = result.release_code == 0
                        ? ExactReserveStatus::moved_address_released
                        : ExactReserveStatus::moved_address_release_failed;
    return result;
  }

  result.status = ExactReserveStatus::ok;
  return result;
}

}  // namespace refrozen::ps5
