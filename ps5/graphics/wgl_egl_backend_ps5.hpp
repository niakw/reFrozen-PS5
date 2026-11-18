// SPDX-License-Identifier: GPL-3.0-or-later
// EGL implementation of the host-independent WGL platform contract.
// The public header deliberately hides EGL types so Win32/WGL code stays
// independent of the selected PS5 OpenGL implementation.
#pragma once

#include "wgl_platform_contract.hpp"

#include <memory>

namespace refrozen::ps5::graphics {

class EglWglBackend {
 public:
  EglWglBackend();
  ~EglWglBackend();

  EglWglBackend(const EglWglBackend&) = delete;
  EglWglBackend& operator=(const EglWglBackend&) = delete;

  [[nodiscard]] WglBackendOps Ops() noexcept;
  [[nodiscard]] bool Ready() const noexcept;
  [[nodiscard]] int Width() const noexcept;
  [[nodiscard]] int Height() const noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;

  static BackendContext CreateContext(void* user, BackendContext share,
                                      int profile_mask);
  static bool DestroyContext(void* user, BackendContext context);
  static bool MakeCurrent(void* user, BackendContext context, DeviceContext dc);
  static bool ClearCurrent(void* user);
  static bool SwapBuffers(void* user, DeviceContext dc);
  static void* GetProcAddress(void* user, const char* name);
};

}  // namespace refrozen::ps5::graphics
