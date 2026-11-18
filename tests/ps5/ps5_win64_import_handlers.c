// SPDX-License-Identifier: GPL-3.0-or-later
// Deterministic native handlers used only by the public synthetic Win64 IAT probe.
#include "cpu.h"

#include <stdint.h>

uint64_t g_refrozen_tick_import_calls = 0;
uint64_t g_refrozen_unimplemented_import_calls = 0;

void I_kernel32_dll_GetTickCount64(CPU* c) {
  ++g_refrozen_tick_import_calls;
  c->rax = UINT64_C(0x123456789abcdef0);
}

// Generated tables contain weak fail-closed import stubs. Keep their fallback
// dependency linkable and observable; the IAT probe must leave this counter 0.
void unimpl_import(CPU* c, const char* name) {
  (void)name;
  ++g_refrozen_unimplemented_import_calls;
  c->rax = UINT64_C(0xdeadbeef);
}
