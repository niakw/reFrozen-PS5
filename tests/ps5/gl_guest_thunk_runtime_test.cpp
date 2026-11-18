// SPDX-License-Identifier: GPL-3.0-or-later
// Executes generated Win64 CPU-state -> native OpenGL thunks against fake GL.
// No graphics driver or proprietary game bytes are involved.
extern "C" {
#include "rt.h"
}
#include <GL/gl.h>

#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

extern "C" {
void I_opengl32_dll_glBegin(CPU*);
void I_opengl32_dll_glEnd(CPU*);
void I_opengl32_dll_glVertex3f(CPU*);
void I_opengl32_dll_glTexCoord2f(CPU*);
void I_opengl32_dll_glColor4ub(CPU*);
void I_opengl32_dll_glMatrixMode(CPU*);
void I_opengl32_dll_glLoadIdentity(CPU*);
void I_opengl32_dll_glOrtho(CPU*);
void I_opengl32_dll_glViewport(CPU*);
void I_opengl32_dll_glClearColor(CPU*);
void I_opengl32_dll_glClear(CPU*);
void I_opengl32_dll_glBindTexture(CPU*);
void I_opengl32_dll_glTexImage2D(CPU*);
void I_opengl32_dll_glGetString(CPU*);
}

namespace refrozen::ps5::graphics {
std::uint64_t ResolveGeneratedGuestGlProc(const char* name);
}

namespace {
struct Calls {
  GLenum begin_mode{};
  int end_count{};
  std::array<GLfloat, 3> vertex{};
  std::array<GLfloat, 2> texcoord{};
  std::array<GLubyte, 4> color{};
  GLenum matrix_mode{};
  int load_identity_count{};
  std::array<GLdouble, 6> ortho{};
  std::array<GLint, 4> viewport{};
  std::array<GLfloat, 4> clear_color{};
  GLbitfield clear_mask{};
  GLenum texture_target{};
  GLuint texture{};
  struct {
    GLenum target{};
    GLint level{};
    GLint internal_format{};
    GLsizei width{};
    GLsizei height{};
    GLint border{};
    GLenum format{};
    GLenum type{};
    const GLvoid* pixels{};
  } tex_image;
  GLenum get_string_name{};
} g_calls;

const GLubyte kRenderer[] = "refrozen-fake-gl";
std::string g_host_name;
gfn g_host_function{};
constexpr std::uint64_t kHostToken = HOSTFN_BASE + UINT64_C(0x1234);

void SetStackU64(CPU& c, int index, std::uint64_t value) {
  assert(index >= 4);
  const std::uintptr_t address =
      static_cast<std::uintptr_t>(c.rsp + 8 + 8 * index);
  std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value));
}
void SetStackDouble(CPU& c, int index, double value) {
  static_assert(sizeof(value) == sizeof(std::uint64_t));
  std::uint64_t bits{};
  std::memcpy(&bits, &value, sizeof(bits));
  SetStackU64(c, index, bits);
}
bool Nearly(double a, double b) { return std::abs(a - b) < 1e-9; }
}  // namespace

extern "C" {

int rt_strict = 0;

std::uint64_t rt_host_fn(gfn function, const char* name) {
  g_host_function = function;
  g_host_name = name ? name : "";
  return kHostToken;
}

void glBegin(GLenum mode) { g_calls.begin_mode = mode; }
void glEnd(void) { ++g_calls.end_count; }
void glVertex3f(GLfloat x, GLfloat y, GLfloat z) { g_calls.vertex = {x, y, z}; }
void glTexCoord2f(GLfloat s, GLfloat t) { g_calls.texcoord = {s, t}; }
void glColor4ub(GLubyte r, GLubyte g, GLubyte b, GLubyte a) {
  g_calls.color = {r, g, b, a};
}
void glMatrixMode(GLenum mode) { g_calls.matrix_mode = mode; }
void glLoadIdentity(void) { ++g_calls.load_identity_count; }
void glOrtho(GLdouble left, GLdouble right, GLdouble bottom, GLdouble top,
             GLdouble near_value, GLdouble far_value) {
  g_calls.ortho = {left, right, bottom, top, near_value, far_value};
}
void glViewport(GLint x, GLint y, GLsizei width, GLsizei height) {
  g_calls.viewport = {x, y, width, height};
}
void glClearColor(GLfloat r, GLfloat g, GLfloat b, GLfloat a) {
  g_calls.clear_color = {r, g, b, a};
}
void glClear(GLbitfield mask) { g_calls.clear_mask = mask; }
void glBindTexture(GLenum target, GLuint texture) {
  g_calls.texture_target = target;
  g_calls.texture = texture;
}
void glTexImage2D(GLenum target, GLint level, GLint internal_format,
                  GLsizei width, GLsizei height, GLint border, GLenum format,
                  GLenum type, const GLvoid* pixels) {
  g_calls.tex_image = {
      target, level, internal_format, width, height, border, format, type, pixels};
}
const GLubyte* glGetString(GLenum name) {
  g_calls.get_string_name = name;
  return kRenderer;
}

}  // extern "C"

int main() {
  alignas(16) std::array<std::byte, 256> stack{};
  CPU c{};
  c.rsp = reinterpret_cast<std::uintptr_t>(stack.data());

  c.rcx = GL_TRIANGLES;
  I_opengl32_dll_glBegin(&c);
  I_opengl32_dll_glEnd(&c);
  assert(g_calls.begin_mode == GL_TRIANGLES && g_calls.end_count == 1);

  c.xmm[0].f[0] = 1.25F;
  c.xmm[1].f[0] = -2.5F;
  c.xmm[2].f[0] = 3.75F;
  I_opengl32_dll_glVertex3f(&c);
  assert(g_calls.vertex[0] == 1.25F && g_calls.vertex[1] == -2.5F &&
         g_calls.vertex[2] == 3.75F);

  c.xmm[0].f[0] = 0.25F;
  c.xmm[1].f[0] = 0.75F;
  I_opengl32_dll_glTexCoord2f(&c);
  assert(g_calls.texcoord[0] == 0.25F && g_calls.texcoord[1] == 0.75F);

  c.rcx = 1;
  c.rdx = 2;
  c.r8 = 3;
  c.r9 = 4;
  I_opengl32_dll_glColor4ub(&c);
  assert((g_calls.color == std::array<GLubyte, 4>{1, 2, 3, 4}));

  c.rcx = GL_PROJECTION;
  I_opengl32_dll_glMatrixMode(&c);
  I_opengl32_dll_glLoadIdentity(&c);
  assert(g_calls.matrix_mode == GL_PROJECTION && g_calls.load_identity_count == 1);

  const std::array<double, 6> ortho = {-10.0, 10.0, -5.0, 5.0, 0.1, 100.0};
  for (int i = 0; i < 4; ++i) c.xmm[i].d[0] = ortho[static_cast<std::size_t>(i)];
  SetStackDouble(c, 4, ortho[4]);
  SetStackDouble(c, 5, ortho[5]);
  I_opengl32_dll_glOrtho(&c);
  for (std::size_t i = 0; i < ortho.size(); ++i)
    assert(Nearly(g_calls.ortho[i], ortho[i]));

  c.rcx = static_cast<std::uint32_t>(-4);
  c.rdx = 7;
  c.r8 = 1920;
  c.r9 = 1080;
  I_opengl32_dll_glViewport(&c);
  assert(g_calls.viewport[0] == -4 && g_calls.viewport[1] == 7 &&
         g_calls.viewport[2] == 1920 && g_calls.viewport[3] == 1080);

  c.xmm[0].f[0] = 0.1F;
  c.xmm[1].f[0] = 0.2F;
  c.xmm[2].f[0] = 0.3F;
  c.xmm[3].f[0] = 1.0F;
  I_opengl32_dll_glClearColor(&c);
  c.rcx = GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT;
  I_opengl32_dll_glClear(&c);
  assert(g_calls.clear_color[3] == 1.0F);
  assert(g_calls.clear_mask == (GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT));

  c.rcx = GL_TEXTURE_2D;
  c.rdx = 77;
  I_opengl32_dll_glBindTexture(&c);
  assert(g_calls.texture_target == GL_TEXTURE_2D && g_calls.texture == 77);

  std::uint32_t pixels = 0xAABBCCDD;
  c.rcx = GL_TEXTURE_2D;
  c.rdx = 2;
  c.r8 = GL_RGBA;
  c.r9 = 64;
  SetStackU64(c, 4, 32);
  SetStackU64(c, 5, 0);
  SetStackU64(c, 6, GL_RGBA);
  SetStackU64(c, 7, GL_UNSIGNED_BYTE);
  SetStackU64(c, 8, reinterpret_cast<std::uintptr_t>(&pixels));
  I_opengl32_dll_glTexImage2D(&c);
  assert(g_calls.tex_image.target == GL_TEXTURE_2D);
  assert(g_calls.tex_image.level == 2);
  assert(g_calls.tex_image.internal_format == GL_RGBA);
  assert(g_calls.tex_image.width == 64 && g_calls.tex_image.height == 32);
  assert(g_calls.tex_image.format == GL_RGBA &&
         g_calls.tex_image.type == GL_UNSIGNED_BYTE);
  assert(g_calls.tex_image.pixels == &pixels);

  c.rcx = GL_RENDERER;
  I_opengl32_dll_glGetString(&c);
  assert(c.rax == reinterpret_cast<std::uintptr_t>(kRenderer));
  assert(g_calls.get_string_name == GL_RENDERER);

  g_host_name.clear();
  g_host_function = nullptr;
  const auto token =
      refrozen::ps5::graphics::ResolveGeneratedGuestGlProc("glClear");
  assert(token == kHostToken);
  assert(g_host_name == "glClear");
  assert(g_host_function == I_opengl32_dll_glClear);
  assert(refrozen::ps5::graphics::ResolveGeneratedGuestGlProc("glNope") == 0);

  std::puts("gl_guest_thunk_runtime: PASS");
  return 0;
}
