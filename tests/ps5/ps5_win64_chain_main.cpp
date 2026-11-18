// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 hardware probe: generated Win64 tables -> exact guest mapping ->
// synthetic PE materialization -> generated entry dispatch -> teardown.
// Contains no Warcraft code or data.
#include "guest_image_mapping_ps5.hpp"
#include "pe_image_materializer.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <span>
#include <string_view>

extern "C" {
#include "tables.h"
extern const unsigned char g_refrozen_synthetic_pe[];
extern const std::size_t g_refrozen_synthetic_pe_size;
}

namespace {
constexpr std::uint64_t kInitialRsp = 0x1000800ULL;
constexpr std::size_t kMaxSyntheticSections = 16;

int Fail(const char* stage, int detail = 0) {
  std::fprintf(stderr,
               "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=%s detail=%d\n",
               stage, detail);
  return 1;
}

bool ReadU32(std::size_t offset, std::uint32_t* out) {
  if (!out || offset > g_refrozen_synthetic_pe_size ||
      sizeof(*out) > g_refrozen_synthetic_pe_size - offset) {
    return false;
  }
  std::memcpy(out, g_refrozen_synthetic_pe + offset, sizeof(*out));
  return true;
}

bool SyntheticHeadersSize(std::size_t* headers_size) {
  if (!headers_size || g_refrozen_synthetic_pe_size < 0x40 ||
      g_refrozen_synthetic_pe[0] != 'M' ||
      g_refrozen_synthetic_pe[1] != 'Z') {
    return false;
  }
  std::uint32_t pe_offset = 0;
  if (!ReadU32(0x3c, &pe_offset) ||
      pe_offset > g_refrozen_synthetic_pe_size ||
      24 > g_refrozen_synthetic_pe_size - pe_offset) {
    return false;
  }
  const auto pe = static_cast<std::size_t>(pe_offset);
  if (g_refrozen_synthetic_pe[pe] != 'P' ||
      g_refrozen_synthetic_pe[pe + 1] != 'E' ||
      g_refrozen_synthetic_pe[pe + 2] != 0 ||
      g_refrozen_synthetic_pe[pe + 3] != 0) {
    return false;
  }
  // IMAGE_OPTIONAL_HEADER64.SizeOfHeaders is +60 from the optional header.
  std::uint32_t value = 0;
  if (!ReadU32(pe + 24 + 60, &value) || !value) return false;
  *headers_size = value;
  return true;
}

gfn FindGeneratedFunction(std::uint64_t address) {
  int lo = 0;
  int hi = ngfuncs - 1;
  while (lo <= hi) {
    const int middle = lo + (hi - lo) / 2;
    if (gfuncs[middle].addr == address) return gfuncs[middle].fn;
    if (gfuncs[middle].addr < address)
      lo = middle + 1;
    else
      hi = middle - 1;
  }
  return nullptr;
}

const GSection* FindSection(std::string_view name) {
  for (int i = 0; i < ngsections; ++i) {
    if (gsections[i].name && name == gsections[i].name) return &gsections[i];
  }
  return nullptr;
}
}  // namespace

int main() {
  if (!gimage_base || !gimage_size || !gentry || ngfuncs <= 0 ||
      ngsections <= 0 ||
      ngsections > static_cast<int>(kMaxSyntheticSections)) {
    return Fail("generated-tables");
  }

  const auto mapping =
      refrozen::ps5::MapGuestImagePs5(gimage_base, gimage_size);
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

  std::array<refrozen::ps5::PeSectionCopy, kMaxSyntheticSections> sections{};
  for (int i = 0; i < ngsections; ++i) {
    const auto& generated = gsections[i];
    sections[static_cast<std::size_t>(i)] = refrozen::ps5::PeSectionCopy{
        generated.name ? std::string_view(generated.name) : std::string_view{},
        generated.va,
        generated.vsize,
        generated.fo,
        generated.fsize,
        generated.flags,
    };
  }
  std::size_t headers_size = 0;
  if (!SyntheticHeadersSize(&headers_size)) {
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.status == refrozen::ps5::DirectBackingReleaseStatus::ok
               ? Fail("pe-headers")
               : 2;
  }

  const refrozen::ps5::PeImageCopyLayout layout{
      gimage_base, gimage_size, headers_size,
      std::span<const refrozen::ps5::PeSectionCopy>(
          sections.data(), static_cast<std::size_t>(ngsections))};
  auto destination = std::span<std::uint8_t>(
      reinterpret_cast<std::uint8_t*>(
          static_cast<std::uintptr_t>(gimage_base)),
      static_cast<std::size_t>(gimage_size));
  const auto source = std::span<const std::uint8_t>(
      reinterpret_cast<const std::uint8_t*>(g_refrozen_synthetic_pe),
      g_refrozen_synthetic_pe_size);
  const auto loaded =
      refrozen::ps5::MaterializePeImage(source, destination, layout);
  if (!loaded.ok()) {
    const int detail = static_cast<int>(loaded.status);
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.status == refrozen::ps5::DirectBackingReleaseStatus::ok
               ? Fail("materialize", detail)
               : 2;
  }

  const GSection* const data_section = FindSection(".data");
  gfn const entry = FindGeneratedFunction(gentry);
  if (!data_section || !entry || data_section->vsize < sizeof(std::uint32_t)) {
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.status == refrozen::ps5::DirectBackingReleaseStatus::ok
               ? Fail("dispatch")
               : 2;
  }

  auto* const value = reinterpret_cast<volatile std::uint32_t*>(
      static_cast<std::uintptr_t>(data_section->va));
  if (*value != 41) {
    const int detail = static_cast<int>(*value);
    const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return released.status == refrozen::ps5::DirectBackingReleaseStatus::ok
               ? Fail("initial-data", detail)
               : 2;
  }

  CPU state{};
  state.rax = UINT64_MAX;
  state.rsp = kInitialRsp;
  entry(&state);

  const std::uint32_t stored = *value;
  const bool semantics_ok =
      stored == 42 && state.rax == 42 &&
      state.rsp == kInitialRsp + 8 && state.fn == gentry;

  const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
  if (released.status != refrozen::ps5::DirectBackingReleaseStatus::ok) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=release status=%d\n",
                 static_cast<int>(released.status));
    return 2;
  }
  if (!semantics_ok) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WIN64_CHAIN pass=0 stage=execute "
                 "stored=%u rax=%llx rsp=%llx fn=%llx entry=%llx\n",
                 static_cast<unsigned>(stored),
                 static_cast<unsigned long long>(state.rax),
                 static_cast<unsigned long long>(state.rsp),
                 static_cast<unsigned long long>(state.fn),
                 static_cast<unsigned long long>(gentry));
    return 1;
  }

  std::fprintf(stderr,
               "REFROZEN_PS5_WIN64_CHAIN pass=1 base=%llx logical=%llx "
               "entry=%llx funcs=%d sections=%d stored=%u\n",
               static_cast<unsigned long long>(gimage_base),
               static_cast<unsigned long long>(gimage_size),
               static_cast<unsigned long long>(gentry),
               ngfuncs, ngsections, static_cast<unsigned>(stored));
  return 0;
}
