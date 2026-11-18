// SPDX-License-Identifier: GPL-3.0-or-later
// Execute code translated from scripts/ps5/synthetic_pe64.py on a host.
// The source PE contains ONLY "mov eax, 42; ret"; no Blizzard files.
#include "cpu.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

extern void F_140001000(CPU *c);

int main(void) {
  CPU state = {0};
  const uint64_t initial_rsp = 0x1000800ULL;
  const uint64_t initial_rcx = 0x123456789ABCDEF0ULL;
  state.rax = UINT64_MAX;   // x86-64 must zero-extend a 32-bit eax write
  state.rcx = initial_rcx;
  state.rsp = initial_rsp;

  F_140001000(&state);

  if (state.rax != 42 || state.rsp != initial_rsp + 8 ||
      state.rcx != initial_rcx || state.fn != 0x140001000ULL) {
    fprintf(stderr,
            "Win64 lifted semantics failed: rax=%" PRIx64 " rsp=%" PRIx64
            " rcx=%" PRIx64 " fn=%" PRIx64 "\n",
            state.rax, state.rsp, state.rcx, state.fn);
    return 1;
  }
  puts("synthetic Win64 lift: executable host semantics PASS");
  return 0;
}
