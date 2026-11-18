// SPDX-License-Identifier: GPL-3.0-or-later
#include "wgl_egl_backend_ps5.hpp"
#include "wgl_platform_contract.hpp"

#include <EGL/egl.h>
#include <EGL/eglext.h>

#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

const EGLDisplay kDisplay =
    reinterpret_cast<EGLDisplay>(static_cast<std::uintptr_t>(0x10));
const EGLConfig kConfig =
    reinterpret_cast<EGLConfig>(static_cast<std::uintptr_t>(0x20));
const EGLSurface kSurface =
    reinterpret_cast<EGLSurface>(static_cast<std::uintptr_t>(0x30));

std::array<EGLint, 16> g_intervals{};
std::size_t g_interval_count = 0;
std::uintptr_t g_next_context = 0x100;
bool g_compat_requested = false;

void DummyGlProc() {}

}  // namespace

extern "C" {

EGLDisplay eglGetDisplay(EGLNativeDisplayType display_id) {
  assert(display_id == EGL_DEFAULT_DISPLAY);
  return kDisplay;
}

EGLBoolean eglInitialize(EGLDisplay display, EGLint* major, EGLint* minor) {
  assert(display == kDisplay);
  if (major) *major = 1;
  if (minor) *minor = 5;
  return EGL_TRUE;
}

EGLBoolean eglBindAPI(EGLenum api) {
  assert(api == EGL_OPENGL_API);
  return EGL_TRUE;
}

EGLBoolean eglChooseConfig(EGLDisplay display, const EGLint* attributes,
                           EGLConfig* configs, EGLint config_size,
                           EGLint* count) {
  assert(display == kDisplay);
  assert(attributes != nullptr);
  assert(config_size >= 1);
  *configs = kConfig;
  *count = 1;
  return EGL_TRUE;
}

EGLSurface eglCreateWindowSurface(EGLDisplay display, EGLConfig config,
                                  EGLNativeWindowType window,
                                  const EGLint* attributes) {
  assert(display == kDisplay);
  assert(config == kConfig);
  (void)window;
  assert(attributes == nullptr);
  return kSurface;
}

EGLBoolean eglQuerySurface(EGLDisplay display, EGLSurface surface,
                           EGLint attribute, EGLint* value) {
  assert(display == kDisplay);
  assert(surface == kSurface);
  assert(value != nullptr);
  if (attribute == EGL_WIDTH) {
    *value = 1920;
    return EGL_TRUE;
  }
  if (attribute == EGL_HEIGHT) {
    *value = 1080;
    return EGL_TRUE;
  }
  return EGL_FALSE;
}

EGLContext eglCreateContext(EGLDisplay display, EGLConfig config,
                            EGLContext share, const EGLint* attributes) {
  assert(display == kDisplay);
  assert(config == kConfig);
  (void)share;
  bool profile_seen = false;
  for (const EGLint* a = attributes; a && *a != EGL_NONE; a += 2) {
    if (a[0] == EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR) {
      profile_seen = true;
      g_compat_requested =
          a[1] == EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT_KHR;
    }
  }
  assert(profile_seen);
  return reinterpret_cast<EGLContext>(g_next_context++);
}

EGLBoolean eglDestroyContext(EGLDisplay display, EGLContext context) {
  assert(display == kDisplay);
  assert(context != EGL_NO_CONTEXT);
  return EGL_TRUE;
}

EGLBoolean eglMakeCurrent(EGLDisplay display, EGLSurface draw, EGLSurface read,
                          EGLContext context) {
  assert(display == kDisplay);
  if (context == EGL_NO_CONTEXT) {
    assert(draw == EGL_NO_SURFACE);
    assert(read == EGL_NO_SURFACE);
  } else {
    assert(draw == kSurface);
    assert(read == kSurface);
  }
  return EGL_TRUE;
}

EGLBoolean eglSwapInterval(EGLDisplay display, EGLint interval) {
  assert(display == kDisplay);
  assert(g_interval_count < g_intervals.size());
  g_intervals[g_interval_count++] = interval;
  return interval >= 0 ? EGL_TRUE : EGL_FALSE;
}

EGLBoolean eglSwapBuffers(EGLDisplay display, EGLSurface surface) {
  assert(display == kDisplay);
  assert(surface == kSurface);
  return EGL_TRUE;
}

__eglMustCastToProperFunctionPointerType eglGetProcAddress(const char* name) {
  if (!name || std::strcmp(name, "glGetString") != 0) return nullptr;
  return &DummyGlProc;
}

EGLBoolean eglDestroySurface(EGLDisplay display, EGLSurface surface) {
  assert(display == kDisplay);
  assert(surface == kSurface);
  return EGL_TRUE;
}

EGLBoolean eglTerminate(EGLDisplay display) {
  assert(display == kDisplay);
  return EGL_TRUE;
}

}  // extern "C"

int main() {
  using namespace refrozen::ps5::graphics;

  EglWglBackend backend;
  WglRegistry registry(MakeEglBackendOps(&backend));

  const WglHandle first =
      registry.CreateContext(kWglContextCompatibilityProfileBit, 0);
  assert(first != 0);
  assert(g_compat_requested);
  assert(backend.Ready());
  assert(backend.Width() == 1920);
  assert(backend.Height() == 1080);

  constexpr DeviceContext kDc = UINT64_C(0x1111);
  assert(registry.MakeCurrent(kDc, first));
  assert(g_interval_count == 1 && g_intervals[0] == 1);

  assert(registry.SetSwapInterval(0));
  assert(g_interval_count == 2 && g_intervals[1] == 0);

  assert(registry.ClearCurrent());
  const WglHandle second =
      registry.CreateContext(kWglContextCompatibilityProfileBit, 0);
  assert(second != 0 && second != first);
  assert(registry.MakeCurrent(kDc, second));

  // The important regression check: MakeCurrent must restore the selected
  // interval (0), not hard-code the default 1.
  assert(g_interval_count == 3 && g_intervals[2] == 0);

  assert(!registry.SetSwapInterval(-1));
  assert(g_interval_count == 3);

  assert(registry.SetSwapInterval(1));
  assert(g_interval_count == 4 && g_intervals[3] == 1);
  assert(registry.GetProcAddress("glGetString") != nullptr);
  assert(registry.SwapBuffers(kDc));

  assert(registry.ClearCurrent());
  assert(registry.MakeCurrent(kDc, first));
  assert(g_interval_count == 5 && g_intervals[4] == 1);
  assert(registry.ClearCurrent());
  assert(registry.DeleteContext(second));
  assert(registry.DeleteContext(first));

  std::puts("wgl_egl_backend_mock: PASS intervals=1,0,0,1,1");
  return 0;
}
