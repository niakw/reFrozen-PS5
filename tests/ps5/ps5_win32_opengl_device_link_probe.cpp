// SPDX-License-Identifier: GPL-3.0-or-later
// Link-only proof for the PS5 OpenGL gfx::Device. Never executed in CI.
#include <cstdarg>
#include <cstdlib>
#include <memory>

#include "runtime/gfx/device.h"

namespace recomp {
bool g_trace = false;
void (*g_fatal_report)(const char*) = nullptr;

[[noreturn]] void FatalF(const char*, ...) { std::abort(); }
void WarnF(const char*, ...) {}
void TraceF(const char*, ...) {}
}  // namespace recomp

int main() {
  std::unique_ptr<recomp::gfx::Device> device =
      recomp::gfx::CreateGpuDevice(nullptr);
  // Construction needs EGL at runtime, so this main is link-only and must
  // never execute in public CI. Referencing the factory keeps the complete
  // vtable and backend dependency graph alive at link time.
  return device ? 0 : 1;
}
