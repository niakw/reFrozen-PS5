// SPDX-License-Identifier: GPL-3.0-or-later
// Ordered PS5 OpenGL/WGL bootstrap for the translated Win64 runtime.
// Called by rt_ps5_frontend_init() before the guest image entry point.
#include "wgl_egl_backend_ps5.hpp"
#include "wgl_guest_runtime_ps5.hpp"
#include "wgl_platform_contract.hpp"

#include <cstdint>
#include <new>

extern "C" void rt_log(const char* fmt, ...);

namespace refrozen::ps5::graphics {

// Generated only from the private/local game's exact GL allowlist. Keeping the
// symbol weak lets public synthetic/runtime builds exercise the WGL registry
// without embedding a game's requested GL surface.
std::uint64_t ResolveGeneratedGuestGlProc(const char* name)
    __attribute__((weak));

namespace {
EglWglBackend* g_backend = nullptr;
WglRegistry* g_registry = nullptr;
}

int InitializeWin64Graphics() noexcept {
  if (g_registry) return 0;

  auto* backend = new (std::nothrow) EglWglBackend();
  if (!backend) {
    rt_log("[ps5/graphics] cannot allocate EGL backend\n");
    return 1;
  }
  if (!backend->Ready()) {
    rt_log("[ps5/graphics] EGL/OpenGL backend is not ready\n");
    delete backend;
    return 2;
  }

  auto* registry = new (std::nothrow) WglRegistry(backend->Ops());
  if (!registry) {
    rt_log("[ps5/graphics] cannot allocate WGL registry\n");
    delete backend;
    return 3;
  }

  InstallWglRegistry(registry);
  if (ResolveGeneratedGuestGlProc)
    InstallGuestGlProcResolver(ResolveGeneratedGuestGlProc);

  g_backend = backend;
  g_registry = registry;
  rt_log("[ps5/graphics] WGL/EGL ready: %dx%d\n",
         backend->Width(), backend->Height());
  return 0;
}

WglRegistry* BootWglRegistry() noexcept { return g_registry; }
EglWglBackend* BootEglBackend() noexcept { return g_backend; }

}  // namespace refrozen::ps5::graphics

extern "C" int rt_ps5_graphics_init(void) {
  return refrozen::ps5::graphics::InitializeWin64Graphics();
}
