// SPDX-License-Identifier: GPL-3.0-or-later
// Linux-only syscall substitutes for executing the PS5 import-chain state
// machine in CI. These do not model PS5 firmware; they only preserve the
// exact-address/direct-backing contracts used by the native adapter.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include "direct_guest_backing.hpp"
#include "exact_guest_reservation.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <sys/mman.h>

namespace {
std::int64_t g_physical = -1;
std::size_t g_physical_bytes = 0;
constexpr std::int64_t kFakePhysical = 0x280000;
}

extern "C" std::int64_t sceKernelGetDirectMemorySize() {
  return 0x100000000LL;
}

extern "C" std::int32_t sceKernelReserveVirtualRange(
    void** address, std::size_t bytes, int flags, std::size_t alignment) {
  assert(address != nullptr);
  assert(flags == 0);
  assert(alignment == refrozen::ps5::kPs5KernelGranule);
  void* const requested = *address;
  void* mapped = mmap(requested, bytes, PROT_NONE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
                      -1, 0);
  if (mapped == MAP_FAILED) return -1;
  *address = mapped;
  return mapped == requested ? 0 : -2;
}

extern "C" std::int32_t sceKernelAllocateDirectMemory(
    std::int64_t lo, std::int64_t hi, std::size_t bytes,
    std::size_t alignment, int type, std::int64_t* physical) {
  assert(lo == 0 && hi > 0);
  assert(bytes != 0);
  assert(alignment == refrozen::ps5::kPs5KernelGranule);
  assert(type == refrozen::ps5::kPs5CpuDirectMemoryType);
  assert(physical != nullptr && g_physical < 0);
  g_physical = kFakePhysical;
  g_physical_bytes = bytes;
  *physical = g_physical;
  return 0;
}

extern "C" std::int32_t sceKernelMapDirectMemory(
    void** address, std::size_t bytes, int prot, int flags,
    std::int64_t physical, std::size_t alignment) {
  assert(address != nullptr);
  assert(bytes == g_physical_bytes);
  assert(prot == (PROT_READ | PROT_WRITE));
  assert(flags == MAP_FIXED);
  assert(physical == g_physical);
  assert(alignment == refrozen::ps5::kPs5KernelGranule);
  void* const requested = *address;
  void* mapped = mmap(requested, bytes, prot,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
  if (mapped == MAP_FAILED) return -1;
  *address = mapped;
  return mapped == requested ? 0 : -2;
}

extern "C" std::int32_t sceKernelReleaseDirectMemory(
    std::int64_t physical, std::size_t bytes) {
  assert(physical == g_physical);
  assert(bytes == g_physical_bytes);
  g_physical = -1;
  g_physical_bytes = 0;
  return 0;
}
