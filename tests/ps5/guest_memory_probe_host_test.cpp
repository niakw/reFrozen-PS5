// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include "guest_memory_probe_ps5.hpp"

#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <sys/mman.h>

namespace {
std::int64_t g_physical = -1;
std::size_t g_physical_bytes = 0;
constexpr std::int64_t kFakePhysical = 0x200000;
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
  if (mapped == MAP_FAILED) return -1;  // output remains unchanged on failure
  *address = mapped;
  return mapped == requested ? 0 : -2;
}

extern "C" std::int32_t sceKernelAllocateDirectMemory(
    std::int64_t lo, std::int64_t hi, std::size_t bytes,
    std::size_t alignment, int type, std::int64_t* physical) {
  assert(lo == 0);
  assert(hi > 0);
  assert(physical != nullptr);
  assert(alignment == refrozen::ps5::kPs5KernelGranule);
  assert(type == refrozen::ps5::kPs5CpuDirectMemoryType);
  assert(g_physical < 0);
  g_physical = kFakePhysical;
  g_physical_bytes = bytes;
  *physical = g_physical;
  return 0;
}

extern "C" std::int32_t sceKernelMapDirectMemory(
    void** address, std::size_t bytes, int prot, int flags,
    std::int64_t physical, std::size_t alignment) {
  assert(address != nullptr);
  assert(physical == g_physical);
  assert(bytes == g_physical_bytes);
  assert(prot == (PROT_READ | PROT_WRITE));
  assert(flags == MAP_FIXED);
  assert(alignment == refrozen::ps5::kPs5KernelGranule);
  void* const requested = *address;
  void* mapped = mmap(requested, bytes, prot,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED,
                      -1, 0);
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

int main() {
  constexpr std::uintptr_t kBase = 0x140000000ULL;
  const auto result = refrozen::ps5::RunSyntheticGuestMemoryProbePs5();
  assert(result.ok());
  assert(result.marker_written == 0x5743335053354D41ULL);
  assert(result.marker_read == result.marker_written);
  assert(result.mapping.reservation.size == 0x8000);
  assert(result.mapping.backing.logical_size == 0x5000);
  assert(result.mapping.backing.mapped_size == 0x8000);
  assert(g_physical == -1 && g_physical_bytes == 0);

  unsigned char resident = 0;
  errno = 0;
  assert(mincore(reinterpret_cast<void*>(kBase), 0x1000, &resident) != 0);
  assert(errno == ENOMEM);

  std::puts("guest_memory_probe_host: PASS");
}
