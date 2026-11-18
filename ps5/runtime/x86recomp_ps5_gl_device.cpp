// SPDX-License-Identifier: GPL-3.0-or-later
// Native PS5 OpenGL gfx::Device for the reFrozen Win32/OpenGL route.
//
// The guest OpenGL semantic layer (runtime/gl/context.cpp) already converts
// OpenGL 1.x state into gfx::FfState/FfDraw. This backend converts that
// fixed-function contract back to the qualified PS5 OpenGL compatibility
// context. It intentionally does not implement D3D9/program/compute paths.
#define GL_GLEXT_PROTOTYPES 1

#include <GL/gl.h>
#include <GL/glext.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

#include "runtime/gfx/device.h"
#include "runtime/log.h"
#include "ps5/graphics/wgl_egl_backend_ps5.hpp"
#include "ps5/graphics/wgl_platform_contract.hpp"

namespace recomp::gfx {
namespace {

using refrozen::ps5::graphics::DeviceContext;
using refrozen::ps5::graphics::EglWglBackend;
using refrozen::ps5::graphics::WglHandle;
using refrozen::ps5::graphics::WglRegistry;
using refrozen::ps5::graphics::kWglContextCompatibilityProfileBit;

// D3D7/D3D9 numeric state used by runtime/gl/context.cpp.
enum : uint32_t {
  RS_ZENABLE = 7, RS_FILLMODE = 8, RS_SHADEMODE = 9, RS_ZWRITEENABLE = 14,
  RS_ALPHATESTENABLE = 15, RS_SRCBLEND = 19, RS_DESTBLEND = 20,
  RS_CULLMODE = 22, RS_ZFUNC = 23, RS_ALPHAREF = 24, RS_ALPHAFUNC = 25,
  RS_ALPHABLENDENABLE = 27, RS_FOGENABLE = 28, RS_FOGCOLOR = 34,
  RS_FOGSTART = 36, RS_FOGEND = 37, RS_FOGDENSITY = 38,
  RS_STENCILENABLE = 52, RS_STENCILFAIL = 53, RS_STENCILZFAIL = 54,
  RS_STENCILPASS = 55, RS_STENCILFUNC = 56, RS_STENCILREF = 57,
  RS_STENCILMASK = 58, RS_STENCILWRITEMASK = 59, RS_TEXTUREFACTOR = 60,
  RS_LIGHTING = 137, RS_AMBIENT = 139, RS_FOGVERTEXMODE = 140,
  RS_COLORVERTEX = 141, RS_LOCALVIEWER = 142, RS_NORMALIZENORMALS = 143,
  RS_DIFFUSEMATERIALSOURCE = 145, RS_SPECULARMATERIALSOURCE = 146,
  RS_AMBIENTMATERIALSOURCE = 147, RS_EMISSIVEMATERIALSOURCE = 148,
  RS_CLIPPLANEENABLE = 152, RS_COLORWRITEENABLE = 168,
  RS_SCISSORTESTENABLE = 174, RS_SLOPESCALEDEPTHBIAS = 175,
  RS_DEPTHBIAS = 195,
};
enum : uint32_t {
  TSS_COLOROP = 1, TSS_COLORARG1 = 2, TSS_COLORARG2 = 3,
  TSS_ALPHAOP = 4, TSS_ALPHAARG1 = 5, TSS_ALPHAARG2 = 6,
  TSS_ADDRESSU = 13, TSS_ADDRESSV = 14, TSS_MAGFILTER = 16,
  TSS_MINFILTER = 17, TSS_MIPFILTER = 18, TSS_MAXANISOTROPY = 21,
  TSS_TEXTURETRANSFORMFLAGS = 24, TSS_COLORARG0 = 26,
  TSS_ALPHAARG0 = 27,
};
enum : uint32_t {
  TOP_DISABLE = 1, TOP_SELECTARG1 = 2, TOP_MODULATE = 4,
  TOP_MODULATE2X = 5, TOP_MODULATE4X = 6, TOP_ADD = 7,
  TOP_ADDSIGNED = 8, TOP_ADDSIGNED2X = 9, TOP_SUBTRACT = 10,
  TOP_BLENDTEXTUREALPHA = 13, TOP_DOTPRODUCT3 = 24, TOP_LERP = 26,
};
enum : uint32_t {
  TA_DIFFUSE = 0, TA_CURRENT = 1, TA_TEXTURE = 2, TA_TFACTOR = 3,
  TA_COMPLEMENT = 0x10, TA_ALPHAREPLICATE = 0x20,
};
enum : uint32_t {
  FVF_XYZ = 0x002, FVF_XYZW = 0x4002, FVF_NORMAL = 0x010,
  FVF_DIFFUSE = 0x040,
  CLEAR_TARGET = 1, CLEAR_ZBUFFER = 2, CLEAR_STENCIL = 4,
};

struct SharedEgl {
  EglWglBackend backend;
  WglRegistry registry{backend.Ops()};
};

SharedEgl& Egl() {
  static SharedEgl shared;
  return shared;
}

std::atomic<uint64_t> g_next_dc{1};

[[noreturn]] void Unsupported(const char* what) {
  FatalF("ps5-gl device: %s is not qualified for the Warcraft 1.26a OpenGL route", what);
  __builtin_unreachable();
}

float FloatOf(uint32_t bits) { return std::bit_cast<float>(bits); }

void Argb(uint32_t c, GLfloat out[4]) {
  out[0] = GLfloat((c >> 16) & 0xFF) / 255.0f;
  out[1] = GLfloat((c >> 8) & 0xFF) / 255.0f;
  out[2] = GLfloat(c & 0xFF) / 255.0f;
  out[3] = GLfloat((c >> 24) & 0xFF) / 255.0f;
}

GLenum Compare(uint32_t v) {
  static constexpr GLenum k[] = {
      GL_ALWAYS, GL_NEVER, GL_LESS, GL_EQUAL, GL_LEQUAL,
      GL_GREATER, GL_NOTEQUAL, GL_GEQUAL, GL_ALWAYS,
  };
  return v < std::size(k) ? k[v] : GL_ALWAYS;
}

GLenum Blend(uint32_t v) {
  switch (v) {
    case 1: return GL_ZERO;
    case 2: return GL_ONE;
    case 3: return GL_SRC_COLOR;
    case 4: return GL_ONE_MINUS_SRC_COLOR;
    case 5: return GL_SRC_ALPHA;
    case 6: return GL_ONE_MINUS_SRC_ALPHA;
    case 7: return GL_DST_ALPHA;
    case 8: return GL_ONE_MINUS_DST_ALPHA;
    case 9: return GL_DST_COLOR;
    case 10: return GL_ONE_MINUS_DST_COLOR;
    case 11: return GL_SRC_ALPHA_SATURATE;
    default: return GL_ONE;
  }
}

GLenum Stencil(uint32_t v) {
  switch (v) {
    case 1: return GL_KEEP;
    case 2: return GL_ZERO;
    case 3: return GL_REPLACE;
    case 4: return GL_INCR;
    case 5: return GL_DECR;
    case 6: return GL_INVERT;
    default: return GL_KEEP;
  }
}

GLenum Primitive(uint32_t p) {
  switch (p) {
    case 1: return GL_POINTS;
    case 2: return GL_LINES;
    case 3: return GL_LINE_STRIP;
    case 4: return GL_TRIANGLES;
    case 5: return GL_TRIANGLE_STRIP;
    case 6: return GL_TRIANGLE_FAN;
    default: return 0;
  }
}

GLenum TexArgSource(uint32_t a) {
  switch (a & 0xF) {
    case TA_DIFFUSE: return GL_PRIMARY_COLOR;
    case TA_CURRENT: return GL_PREVIOUS;
    case TA_TEXTURE: return GL_TEXTURE;
    case TA_TFACTOR: return GL_CONSTANT;
    default: return GL_PREVIOUS;
  }
}

GLenum TexOperand(uint32_t a, bool alpha) {
  const bool complement = (a & TA_COMPLEMENT) != 0;
  const bool replicate_alpha = (a & TA_ALPHAREPLICATE) != 0;
  if (alpha || replicate_alpha)
    return complement ? GL_ONE_MINUS_SRC_ALPHA : GL_SRC_ALPHA;
  return complement ? GL_ONE_MINUS_SRC_COLOR : GL_SRC_COLOR;
}

void ApplyTexArgs(GLenum target, uint32_t arg0, uint32_t arg1, uint32_t arg2,
                  bool alpha) {
  const GLenum src0 = alpha ? GL_SOURCE0_ALPHA : GL_SOURCE0_RGB;
  const GLenum op0 = alpha ? GL_OPERAND0_ALPHA : GL_OPERAND0_RGB;
  const uint32_t args[3] = {arg0, arg1, arg2};
  for (int i = 0; i < 3; ++i) {
    glTexEnvi(GL_TEXTURE_ENV, src0 + i, GLint(TexArgSource(args[i])));
    glTexEnvi(GL_TEXTURE_ENV, op0 + i, GLint(TexOperand(args[i], alpha)));
  }
  (void)target;
}

void ApplyTexCombine(uint32_t op, uint32_t a0, uint32_t a1, uint32_t a2,
                     bool alpha) {
  const GLenum combine = alpha ? GL_COMBINE_ALPHA : GL_COMBINE_RGB;
  GLenum mode = GL_REPLACE;
  GLint scale = 1;
  uint32_t x0 = a1, x1 = a2, x2 = a0;
  switch (op) {
    case TOP_SELECTARG1: mode = GL_REPLACE; x0 = a1; break;
    case TOP_MODULATE: mode = GL_MODULATE; break;
    case TOP_MODULATE2X: mode = GL_MODULATE; scale = 2; break;
    case TOP_MODULATE4X: mode = GL_MODULATE; scale = 4; break;
    case TOP_ADD: mode = GL_ADD; break;
    case TOP_ADDSIGNED: mode = GL_ADD_SIGNED; break;
    case TOP_ADDSIGNED2X: mode = GL_ADD_SIGNED; scale = 2; break;
    case TOP_SUBTRACT: mode = GL_SUBTRACT; break;
    case TOP_BLENDTEXTUREALPHA:
      mode = GL_INTERPOLATE;
      x0 = a1;
      x1 = a2;
      x2 = TA_TEXTURE | TA_ALPHAREPLICATE;
      break;
    case TOP_DOTPRODUCT3:
      mode = alpha ? GL_DOT3_RGBA : GL_DOT3_RGB;
      break;
    case TOP_LERP:
      mode = GL_INTERPOLATE;
      // D3D LERP(a0,a1,a2) = a1*a0 + a2*(1-a0).
      x0 = a1;
      x1 = a2;
      x2 = a0;
      break;
    default:
      Unsupported("texture combine operation");
  }
  glTexEnvi(GL_TEXTURE_ENV, combine, GLint(mode));
  ApplyTexArgs(combine, x0, x1, x2, alpha);
  glTexEnvi(GL_TEXTURE_ENV, alpha ? GL_ALPHA_SCALE : GL_RGB_SCALE, scale);
}

struct GlTexture {
  GLuint name{};
  int w{};
  int h{};
  int levels{};
  Format format{Format::Unknown};
};

struct GlDepth {
  GLuint renderbuffer{};
  int w{};
  int h{};
};

class Ps5GlDevice final : public Device {
 public:
  explicit Ps5GlDevice(SDL_Window*) : dc_(g_next_dc.fetch_add(1)) {
    if (!dc_) dc_ = g_next_dc.fetch_add(1);
    ctx_ = Egl().registry.CreateContext(kWglContextCompatibilityProfileBit);
    if (!ctx_ || !Egl().registry.MakeCurrent(dc_, ctx_))
      FatalF("ps5-gl device: cannot create/make current a compatibility context");
    out_w_ = Egl().backend.Width();
    out_h_ = Egl().backend.Height();
    if (out_w_ <= 0 || out_h_ <= 0)
      FatalF("ps5-gl device: invalid EGL surface size %dx%d", out_w_, out_h_);
  }

  ~Ps5GlDevice() override {
    EnsureCurrent();
    for (auto& [id, tex] : textures_) {
      (void)id;
      if (tex.name) glDeleteTextures(1, &tex.name);
    }
    for (auto& [id, depth] : depths_) {
      (void)id;
      if (depth.renderbuffer) glDeleteRenderbuffers(1, &depth.renderbuffer);
    }
    if (back_color_) glDeleteTextures(1, &back_color_);
    if (back_fbo_) glDeleteFramebuffers(1, &back_fbo_);
    (void)Egl().registry.ClearCurrent();
    if (ctx_) (void)Egl().registry.DeleteContext(ctx_);
  }

  void ResetSwapChain(int w, int h, bool vsync) override {
    EnsureCurrent();
    if (w <= 0 || h <= 0) FatalF("ps5-gl device: invalid swap size %dx%d", w, h);
    bb_w_ = w;
    bb_h_ = h;
    vsync_ = vsync;
    (void)Egl().registry.SetSwapInterval(vsync ? 1 : 0);

    if (!back_fbo_) glGenFramebuffers(1, &back_fbo_);
    if (back_color_) glDeleteTextures(1, &back_color_);
    glGenTextures(1, &back_color_);
    glBindTexture(GL_TEXTURE_2D, back_color_);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_BGRA,
                 GL_UNSIGNED_BYTE, nullptr);
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, back_color_, 0);
    AttachDepth(current_depth_);
    RequireFramebuffer();
    glViewport(0, 0, w, h);
    glDisable(GL_SCISSOR_TEST);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
  }

  TextureId CreateTexture(int w, int h, int levels, Format fmt,
                          bool render_target) override {
    EnsureCurrent();
    if (render_target) Unsupported("render-target texture on the GL1.1 path");
    if (w <= 0 || h <= 0) return 0;
    if (levels <= 0) {
      levels = 1;
      for (int s = std::max(w, h); s > 1; s >>= 1) ++levels;
    }
    GlTexture t{.w=w, .h=h, .levels=levels, .format=fmt};
    glGenTextures(1, &t.name);
    glBindTexture(GL_TEXTURE_2D, t.name);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    for (int level = 0; level < levels; ++level) {
      const int lw = std::max(1, w >> level);
      const int lh = std::max(1, h >> level);
      if (fmt == Format::A8R8G8B8) {
        glTexImage2D(GL_TEXTURE_2D, level, GL_RGBA8, lw, lh, 0,
                     GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
      } else {
        const GLenum internal = CompressedFormat(fmt);
        const GLsizei bytes = GLsizei(RowPitch(fmt, uint32_t(lw)) *
                                      RowCount(fmt, uint32_t(lh)));
        glCompressedTexImage2D(GL_TEXTURE_2D, level, internal, lw, lh, 0,
                               bytes, nullptr);
      }
    }
    const TextureId id = next_texture_++;
    textures_.emplace(id, t);
    return id;
  }

  void DestroyTexture(TextureId id) override {
    EnsureCurrent();
    auto it = textures_.find(id);
    if (it == textures_.end()) return;
    if (it->second.name) glDeleteTextures(1, &it->second.name);
    textures_.erase(it);
  }

  void FillTexture(TextureId, const Rect&, uint32_t) override {
    Unsupported("FillTexture");
  }

  void UpdateTexture(TextureId id, int level, const Rect& r,
                     const void* src, uint32_t pitch) override {
    EnsureCurrent();
    auto it = textures_.find(id);
    if (it == textures_.end() || !src || level < 0 || level >= it->second.levels) return;
    const GlTexture& t = it->second;
    const int w = r.right - r.left;
    const int h = r.bottom - r.top;
    if (w <= 0 || h <= 0) return;
    glBindTexture(GL_TEXTURE_2D, t.name);
    if (t.format == Format::A8R8G8B8) {
      glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
      if (pitch == uint32_t(w * 4)) {
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        glTexSubImage2D(GL_TEXTURE_2D, level, r.left, r.top, w, h,
                        GL_BGRA, GL_UNSIGNED_BYTE, src);
      } else {
        glPixelStorei(GL_UNPACK_ROW_LENGTH, GLint(pitch / 4));
        glTexSubImage2D(GL_TEXTURE_2D, level, r.left, r.top, w, h,
                        GL_BGRA, GL_UNSIGNED_BYTE, src);
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
      }
    } else {
      if (r.left || r.top ||
          w != std::max(1, t.w >> level) || h != std::max(1, t.h >> level))
        Unsupported("partial compressed texture update");
      const GLsizei bytes = GLsizei(RowPitch(t.format, uint32_t(w)) *
                                    RowCount(t.format, uint32_t(h)));
      if (pitch != RowPitch(t.format, uint32_t(w)))
        Unsupported("pitched compressed texture update");
      glCompressedTexSubImage2D(GL_TEXTURE_2D, level, 0, 0, w, h,
                                CompressedFormat(t.format), bytes, src);
    }
  }

  TextureId CreateCubeTexture(int, int, Format) override {
    Unsupported("CreateCubeTexture");
  }
  void UpdateCubeTexture(TextureId, int, int, const Rect&, const void*,
                         uint32_t) override {
    Unsupported("UpdateCubeTexture");
  }

  DepthId CreateDepth(int w, int h, Format fmt) override {
    EnsureCurrent();
    if (fmt != Format::D24S8)
      Unsupported("depth format other than D24S8");
    GlDepth d{.w=w, .h=h};
    glGenRenderbuffers(1, &d.renderbuffer);
    glBindRenderbuffer(GL_RENDERBUFFER, d.renderbuffer);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, w, h);
    const DepthId id = next_depth_++;
    depths_.emplace(id, d);
    return id;
  }

  void DestroyDepth(DepthId id) override {
    EnsureCurrent();
    auto it = depths_.find(id);
    if (it == depths_.end()) return;
    if (current_depth_ == id) current_depth_ = 0;
    if (it->second.renderbuffer) glDeleteRenderbuffers(1, &it->second.renderbuffer);
    depths_.erase(it);
  }

  void SetRenderTarget(TextureId color, DepthId depth) override {
    EnsureCurrent();
    if (color != 0) Unsupported("offscreen render target on GL1.1 path");
    current_depth_ = depth;
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    AttachDepth(depth);
    RequireFramebuffer();
  }

  void SetRenderTargets(const ColorTarget[4], DepthId) override {
    Unsupported("SetRenderTargets");
  }
  void StretchRect(ColorTarget, const Rect&, ColorTarget, const Rect&, bool) override {
    Unsupported("StretchRect");
  }
  void Blit(const void*, uint32_t, Format, const Rect&, const Rect&, bool,
            uint32_t) override {
    Unsupported("Blit");
  }
  void BlitBlend(const void*, uint32_t, const Rect&, const Rect&) override {
    Unsupported("BlitBlend");
  }

  void ReadBack(const Rect& r, void* dst, uint32_t pitch, Format fmt) override {
    EnsureCurrent();
    if (!dst || fmt != Format::A8R8G8B8) Unsupported("ReadBack format");
    const int w = r.right - r.left;
    const int h = r.bottom - r.top;
    if (w <= 0 || h <= 0) return;
    std::vector<uint8_t> pixels(size_t(w) * size_t(h) * 4);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, back_fbo_);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(r.left, bb_h_ - r.bottom, w, h, GL_BGRA,
                 GL_UNSIGNED_BYTE, pixels.data());
    const uint32_t row = uint32_t(w * 4);
    for (int y = 0; y < h; ++y)
      std::memcpy(static_cast<uint8_t*>(dst) + size_t(y) * pitch,
                  pixels.data() + size_t(h - 1 - y) * row, row);
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
  }

  uint32_t StartReadBack(const Rect&) override { Unsupported("StartReadBack"); }
  void FinishReadBack(uint32_t, void*, uint32_t, Format) override {
    Unsupported("FinishReadBack");
  }
  void BlitFront(const void*, uint32_t, Format, const Rect&, const Rect&) override {
    Unsupported("BlitFront");
  }
  void ReadBackFront(const Rect&, void*, uint32_t, Format) override {
    Unsupported("ReadBackFront");
  }
  void PresentFront() override { Unsupported("PresentFront"); }

  void Clear(uint32_t count, const Rect* rects, uint32_t flags,
             uint32_t color, float z, uint32_t stencil) override {
    EnsureCurrent();
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    GLbitfield mask = 0;
    if (flags & CLEAR_TARGET) {
      GLfloat c[4]; Argb(color, c);
      glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
      glClearColor(c[0], c[1], c[2], c[3]);
      mask |= GL_COLOR_BUFFER_BIT;
    }
    if (flags & CLEAR_ZBUFFER) {
      glDepthMask(GL_TRUE);
      glClearDepth(z);
      mask |= GL_DEPTH_BUFFER_BIT;
    }
    if (flags & CLEAR_STENCIL) {
      glStencilMask(0xFFFFFFFFu);
      glClearStencil(GLint(stencil));
      mask |= GL_STENCIL_BUFFER_BIT;
    }
    if (!mask) return;
    if (!count || !rects) {
      glDisable(GL_SCISSOR_TEST);
      glClear(mask);
      return;
    }
    glEnable(GL_SCISSOR_TEST);
    for (uint32_t i = 0; i < count; ++i) {
      const Rect& r = rects[i];
      const int w = std::max(0, r.right - r.left);
      const int h = std::max(0, r.bottom - r.top);
      if (!w || !h) continue;
      glScissor(r.left, bb_h_ - r.bottom, w, h);
      glClear(mask);
    }
  }

  void BeginScene() override { EnsureCurrent(); }
  void EndScene() override {}

  void DrawFf(const FfState& s, const FfDraw& d) override {
    EnsureCurrent();
    if (!d.vertex_count || !d.position.data) return;
    ApplyFixedState(s);
    const GLenum primitive = Primitive(d.prim);
    if (!primitive) Unsupported("fixed-function primitive");
    const uint32_t count = d.indices ? d.index_count : d.vertex_count;
    const int tex_sets = std::min(8u, (d.fvf >> 8) & 0xFu);

    glBegin(primitive);
    for (uint32_t i = 0; i < count; ++i) {
      const uint32_t v = FfIndex(d, i);
      if (d.diffuse.data) {
        const auto* c = static_cast<const uint8_t*>(d.diffuse.data) +
                        size_t(v) * d.diffuse.stride;
        if (d.rgba_colors)
          glColor4ub(c[0], c[1], c[2], c[3]);
        else
          glColor4ub(c[2], c[1], c[0], c[3]);
      }
      if (d.normal.data) {
        const auto* n = reinterpret_cast<const float*>(
            static_cast<const uint8_t*>(d.normal.data) + size_t(v) * d.normal.stride);
        glNormal3fv(n);
      }
      for (int unit = 0; unit < tex_sets; ++unit) {
        if (!d.tex[unit].data) continue;
        const auto* tc = reinterpret_cast<const float*>(
            static_cast<const uint8_t*>(d.tex[unit].data) +
            size_t(v) * d.tex[unit].stride);
        glMultiTexCoord2fv(GL_TEXTURE0 + unit, tc);
      }
      const auto* pos = reinterpret_cast<const float*>(
          static_cast<const uint8_t*>(d.position.data) + size_t(v) * d.position.stride);
      if ((d.fvf & 0x400Eu) == FVF_XYZW)
        glVertex4fv(pos);
      else
        glVertex3fv(pos);
    }
    glEnd();
  }

  void Present() override {
    EnsureCurrent();
    glBindFramebuffer(GL_READ_FRAMEBUFFER, back_fbo_);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
    glDisable(GL_SCISSOR_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    const Rect r = FitRect(bb_w_, bb_h_, out_w_, out_h_);
    glBlitFramebuffer(0, 0, bb_w_, bb_h_,
                      r.left, out_h_ - r.bottom, r.right, out_h_ - r.top,
                      GL_COLOR_BUFFER_BIT, GL_LINEAR);
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    if (!Egl().registry.SwapBuffers(dc_))
      FatalF("ps5-gl device: eglSwapBuffers failed");
  }

  ShaderId CreateShader(const hlsl::Program&) override {
    Unsupported("CreateShader");
  }
  void DestroyShader(ShaderId) override { Unsupported("DestroyShader"); }
  void DrawShader(const ShaderDraw&) override { Unsupported("DrawShader"); }

 private:
  void EnsureCurrent() {
    if (Egl().registry.CurrentContext() != ctx_ ||
        Egl().registry.CurrentDeviceContext() != dc_) {
      if (!Egl().registry.MakeCurrent(dc_, ctx_))
        FatalF("ps5-gl device: cannot restore current EGL context");
    }
  }

  GLenum CompressedFormat(Format fmt) const {
    switch (fmt) {
      case Format::DXT1: return GL_COMPRESSED_RGBA_S3TC_DXT1_EXT;
      case Format::DXT2:
      case Format::DXT3: return GL_COMPRESSED_RGBA_S3TC_DXT3_EXT;
      case Format::DXT4:
      case Format::DXT5: return GL_COMPRESSED_RGBA_S3TC_DXT5_EXT;
      default: Unsupported("texture format");
    }
  }

  void AttachDepth(DepthId id) {
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    GLuint rb = 0;
    if (id) {
      auto it = depths_.find(id);
      if (it == depths_.end()) FatalF("ps5-gl device: unknown depth id %u", id);
      rb = it->second.renderbuffer;
    }
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT,
                              GL_RENDERBUFFER, rb);
  }

  void RequireFramebuffer() {
    const GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (status != GL_FRAMEBUFFER_COMPLETE)
      FatalF("ps5-gl device: framebuffer incomplete: 0x%X", unsigned(status));
  }

  void ApplyMatrices(const FfState& s) {
    glMatrixMode(GL_MODELVIEW);
    glLoadMatrixf(s.world[0]);

    float p[16];
    std::memcpy(p, s.proj, sizeof p);
    const float vw = float(std::max<uint32_t>(s.viewport.width, 1));
    const float vh = float(std::max<uint32_t>(s.viewport.height, 1));
    for (int k = 0; k < 4; ++k) {
      const float w = p[k * 4 + 3];
      p[k * 4 + 0] += w / vw;
      p[k * 4 + 1] -= w / vh;
      p[k * 4 + 2] = 2.0f * p[k * 4 + 2] - w;
    }
    glMatrixMode(GL_PROJECTION);
    glLoadMatrixf(p);
    glMatrixMode(GL_MODELVIEW);
  }

  void ApplyTextureStage(const FfState& s, int unit) {
    glActiveTexture(GL_TEXTURE0 + unit);
    const uint32_t op = s.tss[unit][TSS_COLOROP];
    if (op == TOP_DISABLE) {
      glDisable(GL_TEXTURE_2D);
      return;
    }
    auto it = textures_.find(s.textures[unit]);
    if (!s.textures[unit] || it == textures_.end()) {
      glDisable(GL_TEXTURE_2D);
      return;
    }
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, it->second.name);

    const uint32_t mag = s.tss[unit][TSS_MAGFILTER];
    const uint32_t min = s.tss[unit][TSS_MINFILTER];
    const uint32_t mip = s.tss[unit][TSS_MIPFILTER];
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                    mag == 1 ? GL_NEAREST : GL_LINEAR);
    GLenum min_filter = min == 1 ? GL_NEAREST : GL_LINEAR;
    if (mip == 2) min_filter = min == 1 ? GL_NEAREST_MIPMAP_NEAREST
                                        : GL_LINEAR_MIPMAP_NEAREST;
    if (mip == 3) min_filter = min == 1 ? GL_NEAREST_MIPMAP_LINEAR
                                        : GL_LINEAR_MIPMAP_LINEAR;
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GLint(min_filter));
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
                    s.tss[unit][TSS_ADDRESSU] == 1 ? GL_REPEAT : GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
                    s.tss[unit][TSS_ADDRESSV] == 1 ? GL_REPEAT : GL_CLAMP_TO_EDGE);
#ifdef GL_TEXTURE_MAX_ANISOTROPY_EXT
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT,
                    GLfloat(std::max(1u, s.tss[unit][TSS_MAXANISOTROPY])));
#endif

    GLfloat constant[4];
    Argb(s.rs[RS_TEXTUREFACTOR], constant);
    glTexEnvfv(GL_TEXTURE_ENV, GL_TEXTURE_ENV_COLOR, constant);
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_COMBINE);
    ApplyTexCombine(s.tss[unit][TSS_COLOROP],
                    s.tss[unit][TSS_COLORARG0],
                    s.tss[unit][TSS_COLORARG1],
                    s.tss[unit][TSS_COLORARG2], false);
    ApplyTexCombine(s.tss[unit][TSS_ALPHAOP],
                    s.tss[unit][TSS_ALPHAARG0],
                    s.tss[unit][TSS_ALPHAARG1],
                    s.tss[unit][TSS_ALPHAARG2], true);

    float m[16] = {};
    if (s.tss[unit][TSS_TEXTURETRANSFORMFLAGS]) {
      std::copy_n(s.tex[unit], 8, m);
      std::copy_n(s.tex[unit] + 12, 4, m + 8);
      std::copy_n(s.tex[unit] + 8, 4, m + 12);
    } else {
      m[0] = m[5] = m[10] = m[15] = 1;
    }
    glMatrixMode(GL_TEXTURE);
    glLoadMatrixf(m);
    glMatrixMode(GL_MODELVIEW);
  }

  void ApplyLighting(const FfState& s) {
    if (!s.rs[RS_LIGHTING]) {
      glDisable(GL_LIGHTING);
      for (int i = 0; i < 8; ++i) glDisable(GL_LIGHT0 + i);
      return;
    }
    glEnable(GL_LIGHTING);
    if (s.rs[RS_NORMALIZENORMALS]) glEnable(GL_NORMALIZE);
    else glDisable(GL_NORMALIZE);
    glLightModeli(GL_LIGHT_MODEL_LOCAL_VIEWER, s.rs[RS_LOCALVIEWER] ? GL_TRUE : GL_FALSE);
    GLfloat ambient[4]; Argb(s.rs[RS_AMBIENT] | 0xFF000000u, ambient);
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient);

    const bool diffuse_src = s.rs[RS_DIFFUSEMATERIALSOURCE] != 0;
    const bool ambient_src = s.rs[RS_AMBIENTMATERIALSOURCE] != 0;
    if (s.rs[RS_COLORVERTEX] && (diffuse_src || ambient_src)) {
      glEnable(GL_COLOR_MATERIAL);
      GLenum mode = diffuse_src && ambient_src ? GL_AMBIENT_AND_DIFFUSE
                    : diffuse_src ? GL_DIFFUSE : GL_AMBIENT;
      glColorMaterial(GL_FRONT_AND_BACK, mode);
    } else {
      glDisable(GL_COLOR_MATERIAL);
    }

    auto material = [](GLenum pname, const Color& c) {
      const GLfloat v[4] = {c.r, c.g, c.b, c.a};
      glMaterialfv(GL_FRONT_AND_BACK, pname, v);
    };
    material(GL_DIFFUSE, s.material.diffuse);
    material(GL_AMBIENT, s.material.ambient);
    material(GL_SPECULAR, s.material.specular);
    material(GL_EMISSION, s.material.emissive);
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, s.material.power);

    glPushMatrix();
    glLoadIdentity();
    for (int i = 0; i < 8; ++i) {
      const GLenum light = GL_LIGHT0 + i;
      if (i >= int(s.light_count)) {
        glDisable(light);
        continue;
      }
      glEnable(light);
      const Light& l = s.lights[i];
      auto set_color = [light](GLenum pname, const Color& c) {
        const GLfloat v[4] = {c.r, c.g, c.b, c.a};
        glLightfv(light, pname, v);
      };
      set_color(GL_DIFFUSE, l.diffuse);
      set_color(GL_SPECULAR, l.specular);
      set_color(GL_AMBIENT, l.ambient);
      GLfloat pos[4] = {};
      if (l.type == 3) {
        pos[0] = -l.direction[0]; pos[1] = -l.direction[1];
        pos[2] = -l.direction[2]; pos[3] = 0;
      } else {
        pos[0] = l.position[0]; pos[1] = l.position[1];
        pos[2] = l.position[2]; pos[3] = 1;
      }
      glLightfv(light, GL_POSITION, pos);
      glLightf(light, GL_CONSTANT_ATTENUATION, l.attenuation0);
      glLightf(light, GL_LINEAR_ATTENUATION, l.attenuation1);
      glLightf(light, GL_QUADRATIC_ATTENUATION, l.attenuation2);
      if (l.type == 2) {
        const GLfloat dir[3] = {l.direction[0], l.direction[1], l.direction[2]};
        glLightfv(light, GL_SPOT_DIRECTION, dir);
        glLightf(light, GL_SPOT_CUTOFF, std::clamp(l.phi * 90.0f / 3.14159265f, 0.0f, 90.0f));
      } else {
        glLightf(light, GL_SPOT_CUTOFF, 180.0f);
      }
    }
    glPopMatrix();
  }

  void ApplyFixedState(const FfState& s) {
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    glViewport(GLint(s.viewport.x),
               bb_h_ - GLint(s.viewport.y + s.viewport.height),
               GLsizei(s.viewport.width), GLsizei(s.viewport.height));
    glDepthRange(s.viewport.min_z, s.viewport.max_z);

    if (s.rs[RS_SCISSORTESTENABLE]) {
      glEnable(GL_SCISSOR_TEST);
      glScissor(s.scissor.left, bb_h_ - s.scissor.bottom,
                s.scissor.right - s.scissor.left,
                s.scissor.bottom - s.scissor.top);
    } else glDisable(GL_SCISSOR_TEST);

    if (s.rs[RS_ZENABLE]) glEnable(GL_DEPTH_TEST); else glDisable(GL_DEPTH_TEST);
    glDepthMask(s.rs[RS_ZWRITEENABLE] ? GL_TRUE : GL_FALSE);
    glDepthFunc(Compare(s.rs[RS_ZFUNC]));

    if (s.rs[RS_ALPHABLENDENABLE]) glEnable(GL_BLEND); else glDisable(GL_BLEND);
    glBlendFunc(Blend(s.rs[RS_SRCBLEND]), Blend(s.rs[RS_DESTBLEND]));

    if (s.rs[RS_ALPHATESTENABLE]) {
      glEnable(GL_ALPHA_TEST);
      glAlphaFunc(Compare(s.rs[RS_ALPHAFUNC]),
                  GLfloat(s.rs[RS_ALPHAREF] & 0xFF) / 255.0f);
    } else glDisable(GL_ALPHA_TEST);

    if (s.rs[RS_CULLMODE] == 1) glDisable(GL_CULL_FACE);
    else {
      glEnable(GL_CULL_FACE);
      glFrontFace(GL_CCW);
      glCullFace(s.rs[RS_CULLMODE] == 2 ? GL_BACK : GL_FRONT);
    }
    GLenum poly = s.rs[RS_FILLMODE] == 1 ? GL_POINT
                  : s.rs[RS_FILLMODE] == 2 ? GL_LINE : GL_FILL;
    glPolygonMode(GL_FRONT_AND_BACK, poly);
    glShadeModel(s.rs[RS_SHADEMODE] == 1 ? GL_FLAT : GL_SMOOTH);

    const float factor = FloatOf(s.rs[RS_SLOPESCALEDEPTHBIAS]);
    const float units = FloatOf(s.rs[RS_DEPTHBIAS]) * 16777216.0f;
    if (factor != 0 || units != 0) {
      glEnable(GL_POLYGON_OFFSET_FILL);
      glPolygonOffset(factor, units);
    } else glDisable(GL_POLYGON_OFFSET_FILL);

    const uint32_t mask = s.rs[RS_COLORWRITEENABLE];
    glColorMask((mask & 1) != 0, (mask & 2) != 0,
                (mask & 4) != 0, (mask & 8) != 0);

    if (s.rs[RS_STENCILENABLE]) {
      glEnable(GL_STENCIL_TEST);
      glStencilFunc(Compare(s.rs[RS_STENCILFUNC]), GLint(s.rs[RS_STENCILREF]),
                    GLuint(s.rs[RS_STENCILMASK]));
      glStencilMask(GLuint(s.rs[RS_STENCILWRITEMASK]));
      glStencilOp(Stencil(s.rs[RS_STENCILFAIL]),
                  Stencil(s.rs[RS_STENCILZFAIL]),
                  Stencil(s.rs[RS_STENCILPASS]));
    } else glDisable(GL_STENCIL_TEST);

    if (s.rs[RS_FOGENABLE]) {
      glEnable(GL_FOG);
      const uint32_t mode = s.rs[RS_FOGVERTEXMODE];
      glFogi(GL_FOG_MODE, mode == 3 ? GL_LINEAR : mode == 2 ? GL_EXP2 : GL_EXP);
      GLfloat fc[4]; Argb(s.rs[RS_FOGCOLOR] | 0xFF000000u, fc);
      glFogfv(GL_FOG_COLOR, fc);
      glFogf(GL_FOG_START, FloatOf(s.rs[RS_FOGSTART]));
      glFogf(GL_FOG_END, FloatOf(s.rs[RS_FOGEND]));
      glFogf(GL_FOG_DENSITY, FloatOf(s.rs[RS_FOGDENSITY]));
    } else glDisable(GL_FOG);

    ApplyMatrices(s);
    ApplyLighting(s);

    glPushMatrix();
    glLoadIdentity();
    const uint32_t planes = s.rs[RS_CLIPPLANEENABLE];
    for (int i = 0; i < 6; ++i) {
      const GLenum plane = GL_CLIP_PLANE0 + i;
      if (planes & (1u << i)) {
        const GLdouble eq[4] = {s.clip[i][0], s.clip[i][1], s.clip[i][2], s.clip[i][3]};
        glClipPlane(plane, eq);
        glEnable(plane);
      } else glDisable(plane);
    }
    glPopMatrix();

    for (int unit = 0; unit < 8; ++unit) ApplyTextureStage(s, unit);
    glActiveTexture(GL_TEXTURE0);
  }

  DeviceContext dc_{};
  WglHandle ctx_{};
  int out_w_{};
  int out_h_{};
  int bb_w_{};
  int bb_h_{};
  bool vsync_{};
  GLuint back_fbo_{};
  GLuint back_color_{};
  DepthId current_depth_{};
  TextureId next_texture_{1};
  DepthId next_depth_{1};
  std::unordered_map<TextureId, GlTexture> textures_;
  std::unordered_map<DepthId, GlDepth> depths_;
};

}  // namespace

// Keep the existing x86recomp backend-selection ABI. PS5 builds exclude
// runtime/gfx/gpu_device.cpp and provide this implementation instead.
std::unique_ptr<Device> CreateGpuDevice(SDL_Window* window) {
  return std::make_unique<Ps5GlDevice>(window);
}

}  // namespace recomp::gfx
