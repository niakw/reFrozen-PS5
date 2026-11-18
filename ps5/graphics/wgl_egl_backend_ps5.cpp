// SPDX-License-Identifier: GPL-3.0-or-later
#include "wgl_egl_backend_ps5.hpp"

#include <EGL/egl.h>
#include <EGL/eglext.h>

#include <cstdint>
#include <cstring>
#include <mutex>
#include <unordered_set>

namespace refrozen::ps5::graphics {

struct EglWglBackend::Impl {
  mutable std::mutex mutex;
  EGLDisplay display{EGL_NO_DISPLAY};
  EGLConfig config{};
  EGLSurface surface{EGL_NO_SURFACE};
  std::unordered_set<EGLContext> contexts;
  int width{};
  int height{};
  bool ready{};

  bool Open() {
    if (ready) return true;
    auto fail = [this]() {
      Close();
      return false;
    };
    display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (display == EGL_NO_DISPLAY) return false;

    EGLint major = 0;
    EGLint minor = 0;
    if (!eglInitialize(display, &major, &minor)) return fail();
    if (!eglBindAPI(EGL_OPENGL_API)) return fail();

    constexpr EGLint config_attributes[] = {
        EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
        EGL_RED_SIZE, 8,
        EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8,
        EGL_ALPHA_SIZE, 8,
        EGL_DEPTH_SIZE, 24,
        EGL_STENCIL_SIZE, 8,
        EGL_NONE,
    };
    EGLint count = 0;
    if (!eglChooseConfig(display, config_attributes, &config, 1, &count) ||
        count != 1) {
      return fail();
    }

    surface = eglCreateWindowSurface(display, config, EGLNativeWindowType{}, nullptr);
    if (surface == EGL_NO_SURFACE) return fail();
    if (!eglQuerySurface(display, surface, EGL_WIDTH, &width) ||
        !eglQuerySurface(display, surface, EGL_HEIGHT, &height) ||
        width <= 0 || height <= 0) {
      return fail();
    }

    ready = true;
    return true;
  }

  void Close() {
    if (display == EGL_NO_DISPLAY) return;
    (void)eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    for (EGLContext context : contexts) {
      (void)eglDestroyContext(display, context);
    }
    contexts.clear();
    if (surface != EGL_NO_SURFACE) {
      (void)eglDestroySurface(display, surface);
      surface = EGL_NO_SURFACE;
    }
    (void)eglTerminate(display);
    display = EGL_NO_DISPLAY;
    config = {};
    width = 0;
    height = 0;
    ready = false;
  }
};

EglWglBackend::EglWglBackend() : impl_(std::make_unique<Impl>()) {}

EglWglBackend::~EglWglBackend() {
  std::lock_guard lock(impl_->mutex);
  impl_->Close();
}

WglBackendOps EglWglBackend::Ops() noexcept {
  return {
      .user = this,
      .create_context = &EglWglBackend::CreateContext,
      .destroy_context = &EglWglBackend::DestroyContext,
      .make_current = &EglWglBackend::MakeCurrent,
      .clear_current = &EglWglBackend::ClearCurrent,
      .swap_buffers = &EglWglBackend::SwapBuffers,
      .set_swap_interval = &EglWglBackend::SetSwapInterval,
      .get_proc_address = &EglWglBackend::GetProcAddress,
  };
}

bool EglWglBackend::Ready() const noexcept {
  std::lock_guard lock(impl_->mutex);
  return impl_->ready;
}

int EglWglBackend::Width() const noexcept {
  std::lock_guard lock(impl_->mutex);
  return impl_->width;
}

int EglWglBackend::Height() const noexcept {
  std::lock_guard lock(impl_->mutex);
  return impl_->height;
}

BackendContext EglWglBackend::CreateContext(void* user, BackendContext share,
                                            int profile_mask) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->Open()) return 0;

  const EGLContext shared =
      share ? reinterpret_cast<EGLContext>(static_cast<std::uintptr_t>(share))
            : EGL_NO_CONTEXT;
  if (share && !self.impl_->contexts.contains(shared)) return 0;

  const bool core = (profile_mask & kWglContextCoreProfileBit) != 0 &&
                    (profile_mask & kWglContextCompatibilityProfileBit) == 0;
  const EGLint requested_profile =
      core ? EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR
           : EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT_KHR;
  const EGLint attributes[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4,
      EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR, requested_profile,
      EGL_NONE,
  };
  const EGLContext context =
      eglCreateContext(self.impl_->display, self.impl_->config, shared, attributes);
  if (context == EGL_NO_CONTEXT) return 0;
  self.impl_->contexts.insert(context);
  return static_cast<BackendContext>(
      reinterpret_cast<std::uintptr_t>(context));
}

bool EglWglBackend::DestroyContext(void* user, BackendContext context) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready || !context) return false;

  const EGLContext egl_context =
      reinterpret_cast<EGLContext>(static_cast<std::uintptr_t>(context));
  const auto it = self.impl_->contexts.find(egl_context);
  if (it == self.impl_->contexts.end()) return false;
  if (!eglDestroyContext(self.impl_->display, egl_context)) return false;
  self.impl_->contexts.erase(it);
  return true;
}

bool EglWglBackend::MakeCurrent(void* user, BackendContext context,
                                DeviceContext dc) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready || !context || !dc) return false;
  const EGLContext egl_context =
      reinterpret_cast<EGLContext>(static_cast<std::uintptr_t>(context));
  if (!self.impl_->contexts.contains(egl_context)) return false;
  if (eglMakeCurrent(self.impl_->display, self.impl_->surface,
                     self.impl_->surface, egl_context) != EGL_TRUE) {
    return false;
  }
  return eglSwapInterval(self.impl_->display, 1) == EGL_TRUE;
}

bool EglWglBackend::ClearCurrent(void* user) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready) return true;
  return eglMakeCurrent(self.impl_->display, EGL_NO_SURFACE, EGL_NO_SURFACE,
                        EGL_NO_CONTEXT) == EGL_TRUE;
}

bool EglWglBackend::SwapBuffers(void* user, DeviceContext dc) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready || !dc) return false;
  return eglSwapBuffers(self.impl_->display, self.impl_->surface) == EGL_TRUE;
}

bool EglWglBackend::SetSwapInterval(void* user, int interval) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready) return false;
  // Negative WGL intervals (adaptive vsync) require a tear extension that the
  // PS5 EGL stack must explicitly prove before we expose it. Clamp to the
  // portable EGL semantics for now: 0 = immediate, positive = synchronized.
  if (interval < 0) return false;
  return eglSwapInterval(self.impl_->display, interval) == EGL_TRUE;
}

void* EglWglBackend::GetProcAddress(void* user, const char* name) {
  auto& self = *static_cast<EglWglBackend*>(user);
  std::lock_guard lock(self.impl_->mutex);
  if (!self.impl_->ready || !name || !*name) return nullptr;
  const auto proc = eglGetProcAddress(name);
  void* result = nullptr;
  static_assert(sizeof(result) == sizeof(proc));
  std::memcpy(&result, &proc, sizeof(result));
  return result;
}

}  // namespace refrozen::ps5::graphics
