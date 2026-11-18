// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include "guest_image_mapping_ps5.hpp"
#include "pe_image_materializer.hpp"

extern "C" {
#include "cpu.h"
void F_140001000(CPU* c);
}

#include <array>
#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <span>
#include <sys/mman.h>
#include <vector>

namespace {
std::int64_t g_physical = -1;
std::size_t g_physical_bytes = 0;
constexpr std::int64_t kFakePhysical = 0x240000;
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
  assert(bytes == 0x8000);
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

int main(int argc, char** argv) {
  assert(argc == 2);
  constexpr std::uint64_t kBase = 0x140000000ULL;
  constexpr std::uint64_t kLogicalSize = 0x5000ULL;

  const auto mapping = refrozen::ps5::MapGuestImagePs5(kBase, kLogicalSize);
  assert(mapping.ok());
  assert(mapping.reservation.requested == kBase);
  assert(mapping.reservation.size == 0x8000);
  assert(mapping.backing.address == kBase);
  assert(mapping.backing.logical_size == kLogicalSize);
  assert(mapping.backing.mapped_size == 0x8000);

  std::ifstream input(argv[1], std::ios::binary);
  const std::vector<std::uint8_t> file(
      (std::istreambuf_iterator<char>(input)),
      std::istreambuf_iterator<char>());
  assert(!file.empty());

  const std::array sections{
      refrozen::ps5::PeSectionCopy{
          ".text", kBase + 0x1000, 0x10, 0x400, 0x200, 0x60000020},
      refrozen::ps5::PeSectionCopy{
          ".data", kBase + 0x2000, 0x04, 0x600, 0x200, 0xC0000040},
      refrozen::ps5::PeSectionCopy{
          ".pdata", kBase + 0x3000, 0x0C, 0x800, 0x200, 0x40000040},
      refrozen::ps5::PeSectionCopy{
          ".xdata", kBase + 0x4000, 0x04, 0xA00, 0x200, 0x40000040},
  };
  const refrozen::ps5::PeImageCopyLayout layout{
      kBase, kLogicalSize, 0x400, sections};
  auto destination = std::span<std::uint8_t>(
      reinterpret_cast<std::uint8_t*>(static_cast<std::uintptr_t>(kBase)),
      static_cast<std::size_t>(kLogicalSize));
  const auto loaded =
      refrozen::ps5::MaterializePeImage(file, destination, layout);
  assert(loaded.ok());

  auto* value = reinterpret_cast<volatile std::uint32_t*>(
      static_cast<std::uintptr_t>(kBase + 0x2000));
  assert(*value == 41);

  CPU state{};
  constexpr std::uint64_t kInitialRsp = 0x1000800ULL;
  state.rax = UINT64_MAX;
  state.rsp = kInitialRsp;
  F_140001000(&state);

  assert(*value == 42);
  assert(state.rax == 42);
  assert(state.rsp == kInitialRsp + 8);
  assert(state.fn == 0x140001000ULL);

  const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
  assert(released.status ==
         refrozen::ps5::DirectBackingReleaseStatus::ok);
  assert(g_physical == -1 && g_physical_bytes == 0);

  unsigned char resident = 0;
  errno = 0;
  assert(mincore(reinterpret_cast<void*>(
                     static_cast<std::uintptr_t>(kBase)),
                 0x1000, &resident) != 0);
  assert(errno == ENOMEM);

  std::puts(
      "PS5-wrapper synthetic chain: reserve -> direct map -> PE -> recompiled Win64 -> teardown PASS");
  return 0;
}
