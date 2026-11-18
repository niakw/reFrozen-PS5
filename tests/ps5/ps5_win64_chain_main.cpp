// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 hardware probe: exact guest mapping -> synthetic PE materialization ->
// translated Win64 function -> guest data mutation -> teardown.
// Contains no Warcraft code or data.
#include "guest_image_mapping_ps5.hpp"
#include "pe_image_materializer.hpp"

extern "C" {
#include "cpu.h"
void F_140001000(CPU* c);
extern const unsigned char g_refrozen_synthetic_pe[];
extern const std::size_t g_refrozen_synthetic_pe_size;
}

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>

namespace {
constexpr std::uint64_t kBase = 0x140000000ULL;
constexpr std::uint64_t kLogicalSize = 0x5000ULL;
constexpr std::uint64_t kInitialRsp = 0x1000800ULL;
constexpr std::uint64_t kDataAddress = kBase + 0x2000ULL;

bool Fail(const char* stage, int detail = 0) {
  std::fprintf(stderr,
               "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=%s detail=%d\n",
               stage, detail);
  return false;
}
}  // namespace

int main() {
  const auto mapping = refrozen::ps5::MapGuestImagePs5(kBase, kLogicalSize);
  if (!mapping.ok()) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=map status=%d abort=%d "
                 "reservation=%d backing=%d\n",
                 static_cast<int>(mapping.status),
                 mapping.requires_process_abort() ? 1 : 0,
                 static_cast<int>(mapping.reservation.status),
                 static_cast<int>(mapping.backing.status));
    return mapping.requires_process_abort() ? 2 : 1;
  }

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
      reinterpret_cast<std::uint8_t*>(
          static_cast<std::uintptr_t>(kBase)),
      static_cast<std::size_t>(kLogicalSize));
  const auto source = std::span<const std::uint8_t>(
      reinterpret_cast<const std::uint8_t*>(g_refrozen_synthetic_pe),
      g_refrozen_synthetic_pe_size);
  const auto loaded =
      refrozen::ps5::MaterializePeImage(source, destination, layout);
  if (!loaded.ok()) {
    Fail("materialize", static_cast<int>(loaded.status));
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.ok() ? 1 : 2;
  }

  auto* const value = reinterpret_cast<volatile std::uint32_t*>(
      static_cast<std::uintptr_t>(kDataAddress));
  if (*value != 41) {
    Fail("initial-data", static_cast<int>(*value));
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.ok() ? 1 : 2;
  }

  CPU state{};
  state.rax = UINT64_MAX;
  state.rsp = kInitialRsp;
  F_140001000(&state);

  const std::uint32_t stored = *value;
  const bool semantics_ok =
      stored == 42 && state.rax == 42 &&
      state.rsp == kInitialRsp + 8 &&
      state.fn == 0x140001000ULL;

  const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
  if (!released.ok()) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=release status=%d\n",
                 static_cast<int>(released.status));
    return released.requires_process_abort() ? 2 : 1;
  }
  if (!semantics_ok) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=execute "
                 "stored=%u rax=%llx rsp=%llx fn=%llx\n",
                 static_cast<unsigned>(stored),
                 static_cast<unsigned long long>(state.rax),
                 static_cast<unsigned long long>(state.rsp),
                 static_cast<unsigned long long>(state.fn));
    return 1;
  }

  std::fprintf(stderr,
               "REFROZEN_PS5_WIN64_CHAIN pass=1 base=%llx logical=%llx "
               "stored=%u rax=%llx rsp=%llx fn=%llx\n",
               static_cast<unsigned long long>(kBase),
               static_cast<unsigned long long>(kLogicalSize),
               static_cast<unsigned>(stored),
               static_cast<unsigned long long>(state.rax),
               static_cast<unsigned long long>(state.rsp),
               static_cast<unsigned long long>(state.fn));
  return 0;
}
