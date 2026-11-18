// SPDX-License-Identifier: GPL-3.0-or-later
#include "exact_guest_reservation.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>

using namespace refrozen::ps5;

static_assert(CheckEncoreGuestVaPolicy(0x140000000ULL, 0x02000000ULL) ==
              GuestVaPolicy::allowed);
static_assert(CheckEncoreGuestVaPolicy(0x180000000ULL, 0x02000000ULL) ==
              GuestVaPolicy::allowed);
static_assert(CheckEncoreGuestVaPolicy(0x1ff000000ULL, 0x02000000ULL) ==
              GuestVaPolicy::overlaps_radv_32_window);
static_assert(CheckEncoreGuestVaPolicy(0x4000000000ULL, 0x4000ULL) ==
              GuestVaPolicy::reaches_device_memory_window);

struct Mock {
  int scenario{};
  int release_calls{};
  void* moved = reinterpret_cast<void*>(0x150000000ULL);

  int reserve(void** address, std::size_t, int flags, std::size_t alignment) {
    assert(flags == 0);
    assert(alignment == kPs5KernelGranule);
    if (scenario == 1) return -7;
    if (scenario == 2) {
      *address = moved;
      return -8;
    }
    if (scenario == 3 || scenario == 4) {
      *address = moved;
      return 0;
    }
    return 0;
  }

  int release(void* address, std::size_t) {
    ++release_calls;
    assert(address == moved);
    return scenario == 4 ? -9 : 0;
  }
};

int main() {
  constexpr std::uint64_t base = 0x140000000ULL;
  constexpr std::uint64_t size = 0x200000ULL;

  {
    Mock mock;
    const auto r = ReserveExactGuestRange(
        base, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.ok());
    assert(r.observed == base);
    assert(mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 1};
    const auto r = ReserveExactGuestRange(
        base, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::reserve_failed);
    assert(mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 2};
    const auto r = ReserveExactGuestRange(
        base, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::reserve_failed_mutated_address);
    // Ownership is ambiguous after a failing syscall mutates its output.
    assert(mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 3};
    const auto r = ReserveExactGuestRange(
        base, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::moved_address_released);
    assert(mock.release_calls == 1);
  }
  {
    Mock mock{.scenario = 4};
    const auto r = ReserveExactGuestRange(
        base, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::moved_address_release_failed);
    assert(mock.release_calls == 1);
  }
  {
    Mock mock;
    const auto r = ReserveExactGuestRange(
        0x200000000ULL, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::policy_rejected);
  }
  {
    Mock mock;
    const auto r = ReserveExactGuestRange(
        base + 1, size, kPs5KernelGranule,
        [&](void** a, std::size_t n, int f, std::size_t al) {
          return mock.reserve(a, n, f, al);
        },
        [&](void* a, std::size_t n) { return mock.release(a, n); });
    assert(r.status == ExactReserveStatus::invalid_arguments);
  }

  std::cout << "exact_guest_reservation: PASS\n";
}
