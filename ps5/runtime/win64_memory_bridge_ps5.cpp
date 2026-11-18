// SPDX-License-Identifier: GPL-3.0-or-later
#include "win64_memory_bridge_ps5.h"

#include "guest_image_mapping_ps5.hpp"

#include <cstddef>
#include <cstdint>
#include <pthread.h>

namespace {

constexpr std::size_t kMaxGuestMappings = 32;

struct MappingSlot {
  bool occupied{};
  std::uint64_t base{};
  refrozen::ps5::GuestImageMapping mapping{};
};

pthread_mutex_t g_mapping_mutex = PTHREAD_MUTEX_INITIALIZER;
MappingSlot g_mappings[kMaxGuestMappings];

void ClearInfo(refrozen_ps5_guest_map_info* out, std::uint64_t base,
               std::uint64_t logical_size) {
  if (!out) return;
  *out = {};
  out->base = base;
  out->logical_size = logical_size;
}

void FillNativeInfo(refrozen_ps5_guest_map_info* out,
                    const refrozen::ps5::GuestImageMapping& mapping) {
  if (!out) return;
  out->mapped_size = mapping.backing.mapped_size;
  out->native_status = static_cast<std::int32_t>(mapping.status);
  out->native_map_code = mapping.backing.map_code;
  out->native_allocate_code = mapping.backing.allocate_code;
  out->requires_process_abort = mapping.requires_process_abort() ? 1 : 0;
}

}  // namespace

extern "C" int refrozen_ps5_map_guest_rw(
    std::uint64_t base, std::uint64_t logical_size, std::uint64_t alignment,
    refrozen_ps5_guest_map_info* out) {
  ClearInfo(out, base, logical_size);
  if (!base || !logical_size || !alignment ||
      (alignment & (alignment - 1)) != 0) {
    if (out) out->code = REFROZEN_PS5_GUEST_MAP_INVALID;
    return REFROZEN_PS5_GUEST_MAP_INVALID;
  }

  pthread_mutex_lock(&g_mapping_mutex);
  std::size_t free_slot = kMaxGuestMappings;
  for (std::size_t i = 0; i < kMaxGuestMappings; ++i) {
    if (g_mappings[i].occupied && g_mappings[i].base == base) {
      pthread_mutex_unlock(&g_mapping_mutex);
      if (out) out->code = REFROZEN_PS5_GUEST_MAP_DUPLICATE;
      return REFROZEN_PS5_GUEST_MAP_DUPLICATE;
    }
    if (!g_mappings[i].occupied && free_slot == kMaxGuestMappings) {
      free_slot = i;
    }
  }
  if (free_slot == kMaxGuestMappings) {
    pthread_mutex_unlock(&g_mapping_mutex);
    if (out) out->code = REFROZEN_PS5_GUEST_MAP_TABLE_FULL;
    return REFROZEN_PS5_GUEST_MAP_TABLE_FULL;
  }

  const auto mapping =
      refrozen::ps5::MapGuestImagePs5(base, logical_size, alignment);
  FillNativeInfo(out, mapping);
  if (!mapping.ok()) {
    const int code = mapping.requires_process_abort()
                         ? REFROZEN_PS5_GUEST_MAP_OWNERSHIP_AMBIGUOUS
                         : REFROZEN_PS5_GUEST_MAP_NATIVE_FAILED;
    pthread_mutex_unlock(&g_mapping_mutex);
    if (out) out->code = code;
    return code;
  }

  g_mappings[free_slot].occupied = true;
  g_mappings[free_slot].base = base;
  g_mappings[free_slot].mapping = mapping;
  pthread_mutex_unlock(&g_mapping_mutex);

  if (out) {
    out->code = REFROZEN_PS5_GUEST_MAP_OK;
    out->mapped_size = mapping.backing.mapped_size;
  }
  return REFROZEN_PS5_GUEST_MAP_OK;
}

extern "C" int refrozen_ps5_release_guest_rw(std::uint64_t base) {
  pthread_mutex_lock(&g_mapping_mutex);
  for (std::size_t i = 0; i < kMaxGuestMappings; ++i) {
    auto& slot = g_mappings[i];
    if (!slot.occupied || slot.base != base) continue;

    const auto released =
        refrozen::ps5::ReleaseGuestImagePs5(slot.mapping);
    switch (released.status) {
      case refrozen::ps5::DirectBackingReleaseStatus::ok:
        slot = {};
        pthread_mutex_unlock(&g_mapping_mutex);
        return REFROZEN_PS5_GUEST_RELEASE_OK;
      case refrozen::ps5::DirectBackingReleaseStatus::unmap_failed:
        pthread_mutex_unlock(&g_mapping_mutex);
        return REFROZEN_PS5_GUEST_RELEASE_UNMAP_FAILED;
      case refrozen::ps5::DirectBackingReleaseStatus::physical_release_failed:
        pthread_mutex_unlock(&g_mapping_mutex);
        return REFROZEN_PS5_GUEST_RELEASE_PHYSICAL_FAILED;
      case refrozen::ps5::DirectBackingReleaseStatus::invalid:
        pthread_mutex_unlock(&g_mapping_mutex);
        return REFROZEN_PS5_GUEST_RELEASE_NOT_FOUND;
    }
  }
  pthread_mutex_unlock(&g_mapping_mutex);
  return REFROZEN_PS5_GUEST_RELEASE_NOT_FOUND;
}
