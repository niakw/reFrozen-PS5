// SPDX-License-Identifier: GPL-3.0-or-later
// Compile/link probe against the installed PS5 OpenGL SDK.
// Execution is a separate registered-title hardware gate.
#include "wgl_egl_backend_ps5.hpp"
#include "wgl_platform_contract.hpp"

#include <cstdint>
#include <cstdio>

using namespace refrozen::ps5::graphics;

int main() {
  EglWglBackend backend;
  WglRegistry registry(MakeEglBackendOps(&backend));

  // Exercise the exact compatibility-profile path Warcraft Classic is expected
  // to use. This code is linked in CI but only executed in a registered PS5 title.
  const WglHandle context =
      registry.CreateContext(kWglContextCompatibilityProfileBit, 0);
  if (!context) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_REAL_EGL pass=0 stage=create egl=0x%x\n",
                 static_cast<unsigned>(backend.LastError()));
    return 1;
  }
  constexpr DeviceContext kFullscreenDc = UINT64_C(0x1111);
  if (!registry.MakeCurrent(kFullscreenDc, context)) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_REAL_EGL pass=0 stage=current egl=0x%x\n",
                 static_cast<unsigned>(backend.LastError()));
    return 1;
  }

  void* const gl_get_string = registry.GetProcAddress("glGetString");
  const bool swap_ok = registry.SwapBuffers(kFullscreenDc);
  const bool clear_ok = registry.ClearCurrent();
  const bool delete_ok = registry.DeleteContext(context);
  const bool pass = gl_get_string && swap_ok && clear_ok && delete_ok;

  std::fprintf(stderr,
               "REFROZEN_PS5_REAL_EGL pass=%d proc=%p swap=%d clear=%d delete=%d egl=0x%x\n",
               pass ? 1 : 0, gl_get_string, swap_ok ? 1 : 0,
               clear_ok ? 1 : 0, delete_ok ? 1 : 0,
               static_cast<unsigned>(backend.LastError()));
  return pass ? 0 : 1;
}
