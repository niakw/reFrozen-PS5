// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_memory_probe_ps5.hpp"

#include <cstdint>
#include <cstdio>

namespace refrozen::ps5 {

GuestMemoryProbeResult RunSyntheticGuestMemoryProbePs5(
    std::uint64_t base, std::uint64_t logical_size) {
  GuestMemoryProbeResult out{};
  constexpr std::uint64_t kMarkerOffset = 0x2000ULL;
  constexpr std::uint64_t kMarker = 0x5743335053354D41ULL;  // "WC3PS5MA"

  if (logical_size < kMarkerOffset + sizeof(std::uint64_t)) {
    out.status = GuestMemoryProbeStatus::mapping_failed;
    return out;
  }

  out.mapping = MapGuestImagePs5(base, logical_size);
  if (!out.mapping.ok()) {
    out.status = out.mapping.requires_process_abort()
                     ? GuestMemoryProbeStatus::ownership_ambiguous
                     : GuestMemoryProbeStatus::mapping_failed;
    std::fprintf(stderr,
                 "REFROZEN_PS5_GUEST_PROBE map=failed status=%d reserve=%d backing=%d abort=%d\n",
                 static_cast<int>(out.mapping.status),
                 static_cast<int>(out.mapping.reservation.status),
                 static_cast<int>(out.mapping.backing.status),
                 out.mapping.requires_process_abort() ? 1 : 0);
    return out;
  }

  auto* marker = reinterpret_cast<volatile std::uint64_t*>(
      static_cast<std::uintptr_t>(base + kMarkerOffset));
  *marker = kMarker;
  out.marker_written = kMarker;
  out.marker_read = *marker;

  out.release = ReleaseGuestImagePs5(out.mapping);
  if (out.release.status != DirectBackingReleaseStatus::ok) {
    out.status = GuestMemoryProbeStatus::release_failed;
    std::fprintf(stderr,
                 "REFROZEN_PS5_GUEST_PROBE release=failed status=%d unmap=%d direct_release=%d\n",
                 static_cast<int>(out.release.status),
                 out.release.unmap_code, out.release.release_code);
    return out;
  }

  if (out.marker_read != kMarker) {
    out.status = GuestMemoryProbeStatus::marker_mismatch;
    std::fprintf(stderr,
                 "REFROZEN_PS5_GUEST_PROBE marker=failed wrote=%llx read=%llx\n",
                 static_cast<unsigned long long>(out.marker_written),
                 static_cast<unsigned long long>(out.marker_read));
    return out;
  }

  out.status = GuestMemoryProbeStatus::ok;
  std::fprintf(stderr,
               "REFROZEN_PS5_GUEST_PROBE pass=1 base=%llx logical=%llx mapped=%zx marker=%llx\n",
               static_cast<unsigned long long>(base),
               static_cast<unsigned long long>(logical_size),
               out.mapping.backing.mapped_size,
               static_cast<unsigned long long>(out.marker_read));
  return out;
}

}  // namespace refrozen::ps5
