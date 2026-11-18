// SPDX-License-Identifier: GPL-3.0-or-later
#include "direct_guest_backing_ps5.hpp"

#include <cstddef>
#include <cstdint>
#include <sys/mman.h>

extern "C" {
std::int64_t sceKernelGetDirectMemorySize();
std::int32_t sceKernelAllocateDirectMemory(std::int64_t, std::int64_t,
                                           std::size_t, std::size_t, int,
                                           std::int64_t*);
std::int32_t sceKernelMapDirectMemory(void**, std::size_t, int, int,
                                      std::int64_t, std::size_t);
std::int32_t sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
}

namespace refrozen::ps5 {

DirectGuestBacking MapDirectGuestBackingPs5(
    std::uint64_t address, std::uint64_t logical_size,
    std::uint64_t alignment) {
  return MapDirectGuestBacking(
      address, logical_size, alignment,
      PROT_READ | PROT_WRITE, MAP_FIXED,
      [] { return sceKernelGetDirectMemorySize(); },
      [](std::int64_t lo, std::int64_t hi, std::size_t bytes,
         std::size_t align, int type, std::int64_t* physical) {
        return static_cast<int>(
            sceKernelAllocateDirectMemory(lo, hi, bytes, align, type, physical));
      },
      [](void** target, std::size_t bytes, int prot, int flags,
         std::int64_t physical, std::size_t align) {
        return static_cast<int>(
            sceKernelMapDirectMemory(target, bytes, prot, flags, physical, align));
      },
      [](void* target, std::size_t bytes) {
        return munmap(target, bytes);
      },
      [](std::int64_t physical, std::size_t bytes) {
        return static_cast<int>(sceKernelReleaseDirectMemory(physical, bytes));
      });
}

DirectBackingReleaseResult ReleaseDirectGuestBackingPs5(
    const DirectGuestBacking& backing) {
  return ReleaseDirectGuestBacking(
      backing,
      [](void* target, std::size_t bytes) {
        return munmap(target, bytes);
      },
      [](std::int64_t physical, std::size_t bytes) {
        return static_cast<int>(sceKernelReleaseDirectMemory(physical, bytes));
      });
}

}  // namespace refrozen::ps5
