// SPDX-License-Identifier: GPL-3.0-or-later
// Registered-title hardware probe for reFrozen's WGL->PS5 EGL/OpenGL path.
// No Warcraft data is used.
#include "wgl_egl_backend_ps5.hpp"
#include "wgl_platform_contract.hpp"

#include <GL/gl.h>

#include <cstdint>
#include <cstdio>

extern "C" int sceKernelUsleep(std::uint32_t microseconds);

namespace {

int Fail(const char* stage, GLenum gl_error = GL_NO_ERROR) {
  std::fprintf(stderr,
               "REFROZEN_PS5_WGL_TITLE pass=0 stage=%s gl_error=0x%x\n",
               stage, static_cast<unsigned>(gl_error));
  return 1;
}

}  // namespace

int main() {
  using namespace refrozen::ps5::graphics;

  EglWglBackend backend;
  WglRegistry registry(backend.Ops());

  const WglHandle context =
      registry.CreateContext(kWglContextCompatibilityProfileBit, 0);
  if (!context) return Fail("create-context");

  constexpr DeviceContext kFullscreenDc = UINT64_C(0x1111);
  if (!registry.MakeCurrent(kFullscreenDc, context))
    return Fail("make-current");

  const auto* version =
      reinterpret_cast<const char*>(glGetString(GL_VERSION));
  const auto* renderer =
      reinterpret_cast<const char*>(glGetString(GL_RENDERER));
  if (!version || !renderer) return Fail("gl-identity", glGetError());

  const int width = backend.Width();
  const int height = backend.Height();
  if (width <= 0 || height <= 0) return Fail("surface-size");

  glViewport(0, 0, width, height);
  glDisable(GL_DEPTH_TEST);
  glDisable(GL_CULL_FACE);
  glMatrixMode(GL_PROJECTION);
  glLoadIdentity();
  glOrtho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0);
  glMatrixMode(GL_MODELVIEW);
  glLoadIdentity();

  constexpr int kFrames = 120;
  for (int frame = 0; frame < kFrames; ++frame) {
    glClearColor(0.035f, 0.055f, 0.11f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);

    // Deliberately exercise legacy fixed-function Compatibility behavior.
    glBegin(GL_QUADS);
    glColor3f(0.15f, 0.45f, 0.95f);
    glVertex2f(-0.75f, -0.55f);
    glColor3f(0.35f, 0.80f, 1.00f);
    glVertex2f(0.75f, -0.55f);
    glColor3f(0.80f, 0.95f, 1.00f);
    glVertex2f(0.75f, 0.55f);
    glColor3f(0.25f, 0.60f, 1.00f);
    glVertex2f(-0.75f, 0.55f);
    glEnd();

    const GLenum error = glGetError();
    if (error != GL_NO_ERROR) return Fail("legacy-draw", error);
    if (!registry.SwapBuffers(kFullscreenDc)) return Fail("swap");
    sceKernelUsleep(16000);
  }

  const bool clear_ok = registry.ClearCurrent();
  const bool delete_ok = registry.DeleteContext(context);
  const bool pass = clear_ok && delete_ok;
  std::fprintf(stderr,
               "REFROZEN_PS5_WGL_TITLE pass=%d version=%s renderer=%s "
               "width=%d height=%d frames=%d clear=%d delete=%d\n",
               pass ? 1 : 0, version, renderer, width, height, kFrames,
               clear_ok ? 1 : 0, delete_ok ? 1 : 0);
  return pass ? 0 : 1;
}
