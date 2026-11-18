// SPDX-License-Identifier: GPL-3.0-or-later
// C ABI between the translated Win64 runtime (C) and the PS5 guest-memory
// implementation (C++). No game-specific types or data cross this boundary.
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum refrozen_ps5_guest_map_code {
  REFROZEN_PS5_GUEST_MAP_OK = 0,
  REFROZEN_PS5_GUEST_MAP_INVALID = 1,
  REFROZEN_PS5_GUEST_MAP_DUPLICATE = 2,
  REFROZEN_PS5_GUEST_MAP_TABLE_FULL = 3,
  REFROZEN_PS5_GUEST_MAP_NATIVE_FAILED = 4,
  REFROZEN_PS5_GUEST_MAP_OWNERSHIP_AMBIGUOUS = 5,
};

enum refrozen_ps5_guest_release_code {
  REFROZEN_PS5_GUEST_RELEASE_OK = 0,
  REFROZEN_PS5_GUEST_RELEASE_NOT_FOUND = 1,
  REFROZEN_PS5_GUEST_RELEASE_UNMAP_FAILED = 2,
  REFROZEN_PS5_GUEST_RELEASE_PHYSICAL_FAILED = 3,
};

struct refrozen_ps5_guest_map_info {
  uint64_t base;
  uint64_t logical_size;
  uint64_t mapped_size;
  int32_t code;
  int32_t native_status;
  int32_t native_map_code;
  int32_t native_allocate_code;
  int32_t requires_process_abort;
};

// Maps read/write, non-executable PS5 direct memory exactly at base.
// Calls are serialized internally. On success the bridge retains ownership
// metadata until refrozen_ps5_release_guest_rw(base).
int refrozen_ps5_map_guest_rw(uint64_t base, uint64_t logical_size,
                              uint64_t alignment,
                              struct refrozen_ps5_guest_map_info* out);

// Releases one mapping previously returned by refrozen_ps5_map_guest_rw.
// A failed unmap/release keeps the slot occupied so ownership is never guessed.
int refrozen_ps5_release_guest_rw(uint64_t base);

#ifdef __cplusplus
}  // extern "C"
#endif
