// SPDX-License-Identifier: GPL-3.0-or-later
// Runs code lifted from synthetic_pe64_memory.py with guest data identity-mapped.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "cpu.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

extern void F_140001000(CPU *c);

int main(void) {
  const uintptr_t guest_data = 0x140002000ULL;
  const size_t page = 0x1000;
  void* wanted = (void*)guest_data;
#ifdef MAP_FIXED_NOREPLACE
  void* mapped = mmap(wanted, page, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
#else
#error "MAP_FIXED_NOREPLACE is required: the host test must not overwrite an existing mapping"
#endif
  if (mapped != wanted) {
    fprintf(stderr, "identity map failed wanted=%p got=%p errno=%d (%s)\n",
            wanted, mapped, errno, strerror(errno));
    if (mapped != MAP_FAILED) munmap(mapped, page);
    return 1;
  }

  *(uint32_t*)mapped = 41;
  CPU state = {0};
  const uint64_t initial_rsp = 0x1000800ULL;
  state.rax = UINT64_MAX;
  state.rsp = initial_rsp;

  F_140001000(&state);

  const uint32_t stored = *(uint32_t*)mapped;
  const int unmap_rc = munmap(mapped, page);
  if (state.rax != 42 || stored != 42 ||
      state.rsp != initial_rsp + 8 ||
      state.fn != 0x140001000ULL || unmap_rc != 0) {
    fprintf(stderr,
            "identity memory semantics failed: rax=%" PRIx64
            " stored=%" PRIu32 " rsp=%" PRIx64 " fn=%" PRIx64
            " unmap=%d\n",
            state.rax, stored, state.rsp, state.fn, unmap_rc);
    return 1;
  }
  puts("synthetic Win64 identity-mapped load/store: PASS");
  return 0;
}
