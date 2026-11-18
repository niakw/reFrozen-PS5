// SPDX-License-Identifier: GPL-3.0-or-later
#include "direct_guest_backing.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <sys/mman.h>

using namespace refrozen::ps5;

struct Mock {
  int scenario{};
  int allocate_calls{};
  int map_calls{};
  int unmap_calls{};
  int release_calls{};
  std::int64_t physical = 0x200000;
  void* moved = reinterpret_cast<void*>(0x150000000ULL);

  std::int64_t extent() const { return scenario == 1 ? 0 : 0x100000000LL; }

  int allocate(std::int64_t lo, std::int64_t hi, std::size_t bytes,
               std::size_t alignment, int type, std::int64_t* out) {
    ++allocate_calls;
    assert(lo == 0 && hi > 0 && bytes == 0x8000);
    assert(alignment == kPs5KernelGranule);
    assert(type == kPs5CpuDirectMemoryType);
    if (scenario == 2) return -2;
    *out = physical;
    return 0;
  }

  int map(void** address, std::size_t bytes, int prot, int flags,
          std::int64_t pa, std::size_t alignment) {
    ++map_calls;
    assert(bytes == 0x8000 && prot == (PROT_READ | PROT_WRITE) && flags == MAP_FIXED);
    assert(pa == physical && alignment == kPs5KernelGranule);
    if (scenario == 3) return -3;
    if (scenario == 4) {
      *address = moved;
      return -4;
    }
    if (scenario == 5 || scenario == 6 || scenario == 7) *address = moved;
    return 0;
  }

  int unmap(void* address, std::size_t bytes) {
    ++unmap_calls;
    assert(bytes == 0x8000);
    if (scenario == 6 || scenario == 9) return -6;
    assert(address == moved ||
           address == reinterpret_cast<void*>(0x140000000ULL));
    return 0;
  }

  int release(std::int64_t pa, std::size_t bytes) {
    ++release_calls;
    assert(pa == physical && bytes == 0x8000);
    if (scenario == 7 || scenario == 10) return -7;
    return 0;
  }
};

DirectGuestBacking Run(Mock& mock) {
  return MapDirectGuestBacking(
      0x140000000ULL, 0x5000, kPs5KernelGranule, PROT_READ | PROT_WRITE, MAP_FIXED,
      [&] { return mock.extent(); },
      [&](std::int64_t lo, std::int64_t hi, std::size_t n, std::size_t a,
          int type, std::int64_t* physical) {
        return mock.allocate(lo, hi, n, a, type, physical);
      },
      [&](void** address, std::size_t n, int prot, int flags,
          std::int64_t physical, std::size_t a) {
        return mock.map(address, n, prot, flags, physical, a);
      },
      [&](void* address, std::size_t n) { return mock.unmap(address, n); },
      [&](std::int64_t physical, std::size_t n) {
        return mock.release(physical, n);
      });
}

int main() {
  {
    Mock mock;
    const auto r = Run(mock);
    assert(r.ok());
    assert(r.address == 0x140000000ULL);
    assert(r.logical_size == 0x5000);
    assert(r.mapped_size == 0x8000);
    assert(r.physical == mock.physical);
    assert(mock.allocate_calls == 1 && mock.map_calls == 1);
    assert(mock.unmap_calls == 0 && mock.release_calls == 0);

    const auto released = ReleaseDirectGuestBacking(
        r,
        [&](void* a, std::size_t n) { return mock.unmap(a, n); },
        [&](std::int64_t p, std::size_t n) { return mock.release(p, n); });
    assert(released.status == DirectBackingReleaseStatus::ok);
    assert(mock.unmap_calls == 1 && mock.release_calls == 1);
  }
  {
    Mock mock;
    const auto r = MapDirectGuestBacking(
        0x200000000ULL, 0x5000, kPs5KernelGranule,
        PROT_READ | PROT_WRITE, MAP_FIXED,
        [&] { return mock.extent(); },
        [&](std::int64_t lo, std::int64_t hi, std::size_t n, std::size_t a,
            int type, std::int64_t* physical) {
          return mock.allocate(lo, hi, n, a, type, physical);
        },
        [&](void** address, std::size_t n, int prot, int flags,
            std::int64_t physical, std::size_t a) {
          return mock.map(address, n, prot, flags, physical, a);
        },
        [&](void* address, std::size_t n) { return mock.unmap(address, n); },
        [&](std::int64_t physical, std::size_t n) {
          return mock.release(physical, n);
        });
    assert(r.status == DirectBackingStatus::policy_rejected);
    assert(mock.allocate_calls == 0);
  }
  {
    Mock mock;
    const auto r = MapDirectGuestBacking(
        0x140000001ULL, 0x5000, kPs5KernelGranule,
        PROT_READ | PROT_WRITE, MAP_FIXED,
        [&] { return mock.extent(); },
        [&](std::int64_t lo, std::int64_t hi, std::size_t n, std::size_t a,
            int type, std::int64_t* physical) {
          return mock.allocate(lo, hi, n, a, type, physical);
        },
        [&](void** address, std::size_t n, int prot, int flags,
            std::int64_t physical, std::size_t a) {
          return mock.map(address, n, prot, flags, physical, a);
        },
        [&](void* address, std::size_t n) { return mock.unmap(address, n); },
        [&](std::int64_t physical, std::size_t n) {
          return mock.release(physical, n);
        });
    assert(r.status == DirectBackingStatus::invalid_arguments);
    assert(mock.allocate_calls == 0);
  }
  {
    Mock mock{.scenario = 1};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::extent_unavailable);
    assert(mock.allocate_calls == 0);
  }
  {
    Mock mock{.scenario = 2};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::allocate_failed);
    assert(mock.map_calls == 0 && mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 3};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::map_failed_physical_released);
    assert(r.physical == -1);
    assert(mock.release_calls == 1 && mock.unmap_calls == 0);
  }
  {
    Mock mock{.scenario = 4};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::map_failed_mutated_address);
    assert(r.ownership_ambiguous());
    assert(mock.release_calls == 0 && mock.unmap_calls == 0);
  }
  {
    Mock mock{.scenario = 5};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::wrong_address_cleaned);
    assert(r.physical == -1);
    assert(mock.unmap_calls == 1 && mock.release_calls == 1);
  }
  {
    Mock mock{.scenario = 6};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::wrong_address_unmap_failed);
    assert(r.ownership_ambiguous());
    assert(mock.unmap_calls == 1 && mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 7};
    const auto r = Run(mock);
    assert(r.status == DirectBackingStatus::wrong_address_release_failed);
    assert(mock.unmap_calls == 1 && mock.release_calls == 1);
  }
  {
    Mock mock{.scenario = 9};
    auto r = Run(mock);
    // Mapping succeeds exactly; teardown unmap failure must keep physical.
    mock.scenario = 9;
    const auto released = ReleaseDirectGuestBacking(
        r,
        [&](void* a, std::size_t n) { return mock.unmap(a, n); },
        [&](std::int64_t p, std::size_t n) { return mock.release(p, n); });
    assert(released.status == DirectBackingReleaseStatus::unmap_failed);
    assert(mock.release_calls == 0);
  }
  {
    Mock mock{.scenario = 10};
    auto r = Run(mock);
    mock.scenario = 10;
    const auto released = ReleaseDirectGuestBacking(
        r,
        [&](void* a, std::size_t n) { return mock.unmap(a, n); },
        [&](std::int64_t p, std::size_t n) { return mock.release(p, n); });
    assert(released.status == DirectBackingReleaseStatus::physical_release_failed);
    assert(mock.unmap_calls == 1 && mock.release_calls == 1);
  }

  std::cout << "direct_guest_backing: PASS\n";
}
