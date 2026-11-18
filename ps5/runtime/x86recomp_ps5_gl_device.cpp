// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 OpenGL compatibility implementation of the *pinned reFrozen 1.26a*
// x86recomp gfx::Device ABI (ad1b16b... + reFrozen patches).
//
// The guest OpenGL HLE already converts Win32 OpenGL 1.x semantics into
// D3D7-style Device state. This backend maps that exact state back onto the
// qualified PS5 OpenGL compatibility context. It deliberately does not
// pretend to support the unrelated DirectDraw/D3D9 programmable paths.
#define GL_GLEXT_PROTOTYPES 1

#include <GL/gl.h>
#include <GL/glext.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
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
  FVF_PSIZE = 0x020, FVF_DIFFUSE = 0x040, FVF_SPECULAR = 0x080,
  TS_WORLD = 1, TS_VIEW = 2, TS_PROJECTION = 3, TS_TEXTURE0 = 16,
  CLEAR_TARGET = 1, CLEAR_ZBUFFER = 2, CLEAR_STENCIL = 4,
};

struct SharedEgl {
  EglWglBackend backend;
  WglRegistry registry{backend.Ops()};
};

SharedEgl& Egl() {
  static SharedEgl value;
  return value;
}

std::atomic<uint64_t> g_next_dc{1};

[[noreturn]] void Unsupported(const char* what) {
  FatalF("ps5-gl device: unsupported on Warcraft 1.26a OpenGL route: %s", what);
  __builtin_unreachable();
}

std::array<float, 16> Identity() {
  return {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
}

float FloatOf(uint32_t bits) { return std::bit_cast<float>(bits); }

void Argb(uint32_t c, GLfloat out[4]) {
  out[0] = GLfloat((c >> 16) & 0xffu) / 255.0f;
  out[1] = GLfloat((c >> 8) & 0xffu) / 255.0f;
  out[2] = GLfloat(c & 0xffu) / 255.0f;
  out[3] = GLfloat((c >> 24) & 0xffu) / 255.0f;
}

GLenum Compare(uint32_t v) {
  switch (v) {
    case 1: return GL_NEVER;
    case 2: return GL_LESS;
    case 3: return GL_EQUAL;
    case 4: return GL_LEQUAL;
    case 5: return GL_GREATER;
    case 6: return GL_NOTEQUAL;
    case 7: return GL_GEQUAL;
    default: return GL_ALWAYS;
  }
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

GLenum ArgSource(uint32_t a) {
  switch (a & 0xfu) {
    case TA_DIFFUSE: return GL_PRIMARY_COLOR;
    case TA_CURRENT: return GL_PREVIOUS;
    case TA_TEXTURE: return GL_TEXTURE;
    case TA_TFACTOR: return GL_CONSTANT;
    default: return GL_PREVIOUS;
  }
}

GLenum Operand(uint32_t a, bool alpha) {
  const bool inv = (a & TA_COMPLEMENT) != 0;
  const bool alpha_rep = (a & TA_ALPHAREPLICATE) != 0;
  if (alpha || alpha_rep) return inv ? GL_ONE_MINUS_SRC_ALPHA : GL_SRC_ALPHA;
  return inv ? GL_ONE_MINUS_SRC_COLOR : GL_SRC_COLOR;
}

GLenum DxtFormat(Format f) {
  switch (f) {
    case Format::DXT1: return GL_COMPRESSED_RGBA_S3TC_DXT1_EXT;
    case Format::DXT2:
    case Format::DXT3: return GL_COMPRESSED_RGBA_S3TC_DXT3_EXT;
    case Format::DXT4:
    case Format::DXT5: return GL_COMPRESSED_RGBA_S3TC_DXT5_EXT;
    default: Unsupported("texture format");
  }
}

struct GlTexture {
  GLuint name{};
  int w{};
  int h{};
  int levels{};
  Format format{Format::Unknown};
};

struct GlDepth {
  GLuint name{};
  int w{};
  int h{};
};

class Ps5GlDevice final : public Device {
 public:
  explicit Ps5GlDevice(SDL_Window*) : dc_(g_next_dc.fetch_add(1)) {
    if (!dc_) dc_ = g_next_dc.fetch_add(1);
    ctx_ = Egl().registry.CreateContext(kWglContextCompatibilityProfileBit);
    if (!ctx_ || !Egl().registry.MakeCurrent(dc_, ctx_))
      FatalF("ps5-gl device: cannot create compatibility EGL context");
    out_w_ = Egl().backend.Width();
    out_h_ = Egl().backend.Height();
    if (out_w_ <= 0 || out_h_ <= 0)
      FatalF("ps5-gl device: invalid EGL surface %dx%d", out_w_, out_h_);

    world_ = Identity();
    view_ = Identity();
    projection_ = Identity();
    for (auto& m : texture_matrices_) m = Identity();
    rs_.fill(0);
    for (auto& s : tss_) s.fill(0);
  }

  ~Ps5GlDevice() override {
    EnsureCurrent();
    for (auto& [id, t] : textures_) {
      (void)id;
      if (t.name) glDeleteTextures(1, &t.name);
    }
    for (auto& [id, d] : depths_) {
      (void)id;
      if (d.name) glDeleteRenderbuffers(1, &d.name);
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
    (void)Egl().registry.SetSwapInterval(vsync ? 1 : 0);
    if (!back_fbo_) glGenFramebuffers(1, &back_fbo_);
    if (back_color_) glDeleteTextures(1, &back_color_);
    glGenTextures(1, &back_color_);
    glBindTexture(GL_TEXTURE_2D, back_color_);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0,
                 GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, back_color_, 0);
    AttachDepth(current_depth_);
    RequireFramebuffer();
    viewport_ = {0, 0, uint32_t(w), uint32_t(h), 0.0f, 1.0f};
  }

  TextureId CreateTexture(int w, int h, int levels, Format fmt,
                          bool render_target) override {
    EnsureCurrent();
    if (render_target) Unsupported("render-target texture");
    if (w <= 0 || h <= 0) return 0;
    if (fmt != Format::A8R8G8B8 && !IsCompressed(fmt))
      Unsupported("non-ARGB/non-DXT texture");
    if (levels <= 0) {
      levels = 1;
      for (int s = std::max(w, h); s > 1; s >>= 1) ++levels;
    }
    GlTexture t{.w=w, .h=h, .levels=levels, .format=fmt};
    glGenTextures(1, &t.name);
    glBindTexture(GL_TEXTURE_2D, t.name);
    for (int level = 0; level < levels; ++level) {
      const int lw = std::max(1, w >> level);
      const int lh = std::max(1, h >> level);
      if (fmt == Format::A8R8G8B8) {
        glTexImage2D(GL_TEXTURE_2D, level, GL_RGBA8, lw, lh, 0,
                     GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
      } else {
        const GLsizei bytes = GLsizei(RowPitch(fmt, uint32_t(lw)) *
                                      RowCount(fmt, uint32_t(lh)));
        glCompressedTexImage2D(GL_TEXTURE_2D, level, DxtFormat(fmt),
                               lw, lh, 0, bytes, nullptr);
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
    for (auto& t : bound_textures_) if (t == id) t = 0;
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
      if ((pitch & 3u) != 0) Unsupported("unaligned ARGB pitch");
      glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
      glPixelStorei(GL_UNPACK_ROW_LENGTH, GLint(pitch / 4));
      glTexSubImage2D(GL_TEXTURE_2D, level, r.left, r.top, w, h,
                      GL_BGRA, GL_UNSIGNED_BYTE, src);
      glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    } else {
      const uint32_t expected = RowPitch(t.format, uint32_t(w));
      if (r.left || r.top || pitch != expected ||
          w != std::max(1, t.w >> level) || h != std::max(1, t.h >> level))
        Unsupported("partial/pitched DXT update");
      const GLsizei bytes = GLsizei(expected * RowCount(t.format, uint32_t(h)));
      glCompressedTexSubImage2D(GL_TEXTURE_2D, level, 0, 0, w, h,
                                DxtFormat(t.format), bytes, src);
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
    if (fmt != Format::D24S8) Unsupported("depth format");
    GlDepth d{.w=w, .h=h};
    glGenRenderbuffers(1, &d.name);
    glBindRenderbuffer(GL_RENDERBUFFER, d.name);
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
    if (it->second.name) glDeleteRenderbuffers(1, &it->second.name);
    depths_.erase(it);
  }

  void SetRenderTarget(TextureId color, DepthId depth) override {
    EnsureCurrent();
    if (color != 0) Unsupported("offscreen render target");
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
    if (!dst || (fmt != Format::A8R8G8B8 && fmt != Format::X8R8G8B8))
      Unsupported("ReadBack format");
    const int w = r.right - r.left;
    const int h = r.bottom - r.top;
    if (w <= 0 || h <= 0) return;
    if (pitch < uint32_t(w * 4)) Unsupported("ReadBack pitch");
    std::vector<uint8_t> pixels(size_t(w) * size_t(h) * 4);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, back_fbo_);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(r.left, bb_h_ - r.bottom, w, h, GL_BGRA,
                 GL_UNSIGNED_BYTE, pixels.data());
    const size_t row = size_t(w) * 4;
    for (int y = 0; y < h; ++y)
      std::memcpy(static_cast<uint8_t*>(dst) + size_t(y) * pitch,
                  pixels.data() + size_t(h - 1 - y) * row, row);
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

  void SetRenderState(uint32_t state, uint32_t value) override {
    if (state >= rs_.size()) FatalF("ps5-gl device: render state %u out of range", state);
    rs_[state] = value;
  }

  void SetTextureStageState(uint32_t stage, uint32_t type,
                            uint32_t value) override {
    if (stage >= tss_.size() || type >= tss_[0].size())
      FatalF("ps5-gl device: texture state %u/%u out of range", stage, type);
    tss_[stage][type] = value;
  }

  void SetTexture(uint32_t stage, TextureId id) override {
    if (stage >= bound_textures_.size())
      FatalF("ps5-gl device: texture stage %u out of range", stage);
    if (id && !textures_.contains(id))
      FatalF("ps5-gl device: unknown texture id %u", id);
    bound_textures_[stage] = id;
  }

  void SetTransform(uint32_t type, const float m[16]) override {
    if (!m) return;
    if (type == TS_WORLD) std::copy_n(m, 16, world_.data());
    else if (type == TS_VIEW) std::copy_n(m, 16, view_.data());
    else if (type == TS_PROJECTION) std::copy_n(m, 16, projection_.data());
    else if (type >= TS_TEXTURE0 && type < TS_TEXTURE0 + 8)
      std::copy_n(m, 16, texture_matrices_[type - TS_TEXTURE0].data());
    else
      Unsupported("transform type");
  }

  void SetViewport(const Viewport& v) override { viewport_ = v; }
  void SetScissor(const Rect& r) override { scissor_ = r; }
  void SetMaterial(const Material& m) override { material_ = m; }

  void SetLight(uint32_t index, const Light& l) override {
    if (index >= lights_.size()) FatalF("ps5-gl device: light %u out of range", index);
    lights_[index] = l;
    light_valid_[index] = true;
  }

  void LightEnable(uint32_t index, bool enable) override {
    if (index >= light_enabled_.size())
      FatalF("ps5-gl device: light %u out of range", index);
    light_enabled_[index] = enable;
  }

  void SetClipPlane(uint32_t index, const float plane[4]) override {
    if (index >= clip_planes_.size() || !plane)
      FatalF("ps5-gl device: clip plane %u invalid", index);
    std::copy_n(plane, 4, clip_planes_[index].data());
  }

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
      glStencilMask(~GLuint(0));
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

  void Draw(uint32_t prim, uint32_t fvf, const void* vertices,
            uint32_t vertex_count, uint32_t stride,
            const uint16_t* indices, uint32_t index_count) override {
    EnsureCurrent();
    if (!vertices || !vertex_count) return;
    const GLenum mode = Primitive(prim);
    if (!mode) Unsupported("primitive type");
    ApplyState();

    const uint32_t draws = indices ? index_count : vertex_count;
    const auto* base = static_cast<const uint8_t*>(vertices);
    glBegin(mode);
    for (uint32_t i = 0; i < draws; ++i) {
      uint32_t vi = indices ? indices[i] : i;
      if (vi >= vertex_count) vi = vertex_count - 1;
      const uint8_t* p = base + size_t(vi) * stride;

      const bool xyzw = (fvf & 0x400Eu) == FVF_XYZW;
      const int pos_floats = xyzw ? 4 : 3;
      const float* pos = reinterpret_cast<const float*>(p);
      p += size_t(pos_floats) * sizeof(float);

      if (fvf & FVF_NORMAL) {
        const float* n = reinterpret_cast<const float*>(p);
        glNormal3fv(n);
        p += 3 * sizeof(float);
      }
      if (fvf & FVF_PSIZE) p += 4;
      if (fvf & FVF_DIFFUSE) {
        // Guest GL HLE writes D3DCOLOR memory order B,G,R,A.
        glColor4ub(p[2], p[1], p[0], p[3]);
        p += 4;
      }
      if (fvf & FVF_SPECULAR) p += 4;

      const uint32_t tex_count = std::min<uint32_t>((fvf >> 8) & 0xfu, 8);
      for (uint32_t unit = 0; unit < tex_count; ++unit) {
        const float* tc = reinterpret_cast<const float*>(p);
        glMultiTexCoord2fv(GL_TEXTURE0 + unit, tc);
        // The 1.26a GL HLE generates two-component texture coordinates.
        p += 2 * sizeof(float);
      }

      if (xyzw) glVertex4fv(pos);
      else glVertex3fv(pos);
    }
    glEnd();
  }

  Mapped MapDraw(uint32_t vertex_count, uint32_t stride,
                 uint32_t index_count) override {
    if (stride && vertex_count >
        std::numeric_limits<size_t>::max() / size_t(stride))
      FatalF("ps5-gl device: mapped draw size overflow");
    mapped_vertices_.assign(size_t(vertex_count) * stride, 0);
    mapped_indices_.assign(index_count, 0);
    mapped_vertex_count_ = vertex_count;
    mapped_index_count_ = index_count;
    mapped_stride_ = stride;
    return {
        .vertices = mapped_vertices_.empty() ? nullptr : mapped_vertices_.data(),
        .indices = mapped_indices_.empty() ? nullptr : mapped_indices_.data(),
    };
  }

  void DrawMapped(uint32_t prim, uint32_t fvf) override {
    Draw(prim, fvf, mapped_vertices_.data(), mapped_vertex_count_, mapped_stride_,
         mapped_indices_.empty() ? nullptr : mapped_indices_.data(),
         mapped_index_count_);
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
                      r.left, out_h_ - r.bottom,
                      r.right, out_h_ - r.top,
                      GL_COLOR_BUFFER_BIT, GL_LINEAR);
    NotePresentation({bb_w_, bb_h_, out_w_, out_h_, r});
    if (!Egl().registry.SwapBuffers(dc_))
      FatalF("ps5-gl device: eglSwapBuffers failed");
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
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
        FatalF("ps5-gl device: cannot restore current context");
    }
  }

  void AttachDepth(DepthId id) {
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);
    GLuint rb = 0;
    if (id) {
      const auto it = depths_.find(id);
      if (it == depths_.end()) FatalF("ps5-gl device: unknown depth id %u", id);
      rb = it->second.name;
    }
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT,
                              GL_RENDERBUFFER, rb);
  }

  void RequireFramebuffer() {
    const GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (status != GL_FRAMEBUFFER_COMPLETE)
      FatalF("ps5-gl device: framebuffer incomplete 0x%X", unsigned(status));
  }

  void ApplyMatrices() {
    glMatrixMode(GL_MODELVIEW);
    // D3D row-vector WORLD*VIEW corresponds to VIEW*WORLD in the
    // column-vector convention used by compatibility OpenGL.
    glLoadMatrixf(view_.data());
    glMultMatrixf(world_.data());

    std::array<float, 16> p = projection_;
    const float vw = float(std::max<uint32_t>(viewport_.width, 1));
    const float vh = float(std::max<uint32_t>(viewport_.height, 1));
    for (int k = 0; k < 4; ++k) {
      const float w = p[k * 4 + 3];
      p[k * 4 + 0] += w / vw;
      p[k * 4 + 1] -= w / vh;
      p[k * 4 + 2] = 2.0f * p[k * 4 + 2] - w;
    }
    glMatrixMode(GL_PROJECTION);
    glLoadMatrixf(p.data());
    glMatrixMode(GL_MODELVIEW);
  }

  void ApplyTextureStage(uint32_t unit) {
    glActiveTexture(GL_TEXTURE0 + unit);
    const uint32_t op = tss_[unit][TSS_COLOROP];
    const TextureId id = bound_textures_[unit];
    if (op == TOP_DISABLE || !id) {
      glDisable(GL_TEXTURE_2D);
      return;
    }
    const auto it = textures_.find(id);
    if (it == textures_.end()) FatalF("ps5-gl device: texture %u vanished", id);
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, it->second.name);

    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                    tss_[unit][TSS_MAGFILTER] == 1 ? GL_NEAREST : GL_LINEAR);
    GLenum min_filter = tss_[unit][TSS_MINFILTER] == 1 ? GL_NEAREST : GL_LINEAR;
    if (tss_[unit][TSS_MIPFILTER] == 2)
      min_filter = tss_[unit][TSS_MINFILTER] == 1
          ? GL_NEAREST_MIPMAP_NEAREST : GL_LINEAR_MIPMAP_NEAREST;
    else if (tss_[unit][TSS_MIPFILTER] == 3)
      min_filter = tss_[unit][TSS_MINFILTER] == 1
          ? GL_NEAREST_MIPMAP_LINEAR : GL_LINEAR_MIPMAP_LINEAR;
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GLint(min_filter));
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
                    tss_[unit][TSS_ADDRESSU] == 1 ? GL_REPEAT : GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
                    tss_[unit][TSS_ADDRESSV] == 1 ? GL_REPEAT : GL_CLAMP_TO_EDGE);
#ifdef GL_TEXTURE_MAX_ANISOTROPY_EXT
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT,
                    GLfloat(std::max(1u, tss_[unit][TSS_MAXANISOTROPY])));
#endif

    GLfloat constant[4]; Argb(rs_[RS_TEXTUREFACTOR], constant);
    glTexEnvfv(GL_TEXTURE_ENV, GL_TEXTURE_ENV_COLOR, constant);
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_COMBINE);

    ApplyCombine(unit, false);
    ApplyCombine(unit, true);

    std::array<float,16> m = Identity();
    if (tss_[unit][TSS_TEXTURETRANSFORMFLAGS]) {
      const auto& d = texture_matrices_[unit];
      std::copy_n(d.data(), 8, m.data());
      std::copy_n(d.data() + 12, 4, m.data() + 8);
      std::copy_n(d.data() + 8, 4, m.data() + 12);
    }
    glMatrixMode(GL_TEXTURE);
    glLoadMatrixf(m.data());
    glMatrixMode(GL_MODELVIEW);
  }

  void ApplyCombine(uint32_t unit, bool alpha) {
    const uint32_t op = tss_[unit][alpha ? TSS_ALPHAOP : TSS_COLOROP];
    const uint32_t a0 = tss_[unit][alpha ? TSS_ALPHAARG0 : TSS_COLORARG0];
    const uint32_t a1 = tss_[unit][alpha ? TSS_ALPHAARG1 : TSS_COLORARG1];
    const uint32_t a2 = tss_[unit][alpha ? TSS_ALPHAARG2 : TSS_COLORARG2];

    if (alpha && op == TOP_DOTPRODUCT3 &&
        tss_[unit][TSS_COLOROP] == TOP_DOTPRODUCT3) return;

    GLenum mode = GL_REPLACE;
    GLint scale = 1;
    uint32_t x0 = a1, x1 = a2, x2 = a0;
    switch (op) {
      case TOP_SELECTARG1: mode = GL_REPLACE; break;
      case TOP_MODULATE: mode = GL_MODULATE; break;
      case TOP_MODULATE2X: mode = GL_MODULATE; scale = 2; break;
      case TOP_MODULATE4X: mode = GL_MODULATE; scale = 4; break;
      case TOP_ADD: mode = GL_ADD; break;
      case TOP_ADDSIGNED: mode = GL_ADD_SIGNED; break;
      case TOP_ADDSIGNED2X: mode = GL_ADD_SIGNED; scale = 2; break;
      case TOP_SUBTRACT: mode = GL_SUBTRACT; break;
      case TOP_BLENDTEXTUREALPHA:
        mode = GL_INTERPOLATE;
        x2 = TA_TEXTURE | TA_ALPHAREPLICATE;
        break;
      case TOP_DOTPRODUCT3:
        mode = alpha ? GL_DOT3_RGBA :
               (tss_[unit][TSS_ALPHAOP] == TOP_DOTPRODUCT3
                    ? GL_DOT3_RGBA : GL_DOT3_RGB);
        break;
      case TOP_LERP:
        mode = GL_INTERPOLATE;
        x0 = a1; x1 = a2; x2 = a0;
        break;
      default:
        Unsupported("texture combine op");
    }

    const GLenum combine = alpha ? GL_COMBINE_ALPHA : GL_COMBINE_RGB;
    glTexEnvi(GL_TEXTURE_ENV, combine, GLint(mode));
    const GLenum src0 = alpha ? GL_SOURCE0_ALPHA : GL_SOURCE0_RGB;
    const GLenum opd0 = alpha ? GL_OPERAND0_ALPHA : GL_OPERAND0_RGB;
    const uint32_t args[3] = {x0, x1, x2};
    for (int i = 0; i < 3; ++i) {
      glTexEnvi(GL_TEXTURE_ENV, src0 + i, GLint(ArgSource(args[i])));
      glTexEnvi(GL_TEXTURE_ENV, opd0 + i, GLint(Operand(args[i], alpha)));
    }
    glTexEnvi(GL_TEXTURE_ENV, alpha ? GL_ALPHA_SCALE : GL_RGB_SCALE, scale);
  }

  void ApplyLighting() {
    if (!rs_[RS_LIGHTING]) {
      glDisable(GL_LIGHTING);
      for (int i = 0; i < 8; ++i) glDisable(GL_LIGHT0 + i);
      return;
    }
    glEnable(GL_LIGHTING);
    if (rs_[RS_NORMALIZENORMALS]) glEnable(GL_NORMALIZE);
    else glDisable(GL_NORMALIZE);

    GLfloat ambient[4]; Argb(rs_[RS_AMBIENT] | 0xff000000u, ambient);
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient);
    glLightModeli(GL_LIGHT_MODEL_LOCAL_VIEWER,
                  rs_[RS_LOCALVIEWER] ? GL_TRUE : GL_FALSE);

    GLenum cm = 0;
    if (rs_[RS_COLORVERTEX]) {
      const bool d = rs_[RS_DIFFUSEMATERIALSOURCE] != 0;
      const bool a = rs_[RS_AMBIENTMATERIALSOURCE] != 0;
      const bool s = rs_[RS_SPECULARMATERIALSOURCE] != 0;
      const bool e = rs_[RS_EMISSIVEMATERIALSOURCE] != 0;
      if (d && a) cm = GL_AMBIENT_AND_DIFFUSE;
      else if (d) cm = GL_DIFFUSE;
      else if (a) cm = GL_AMBIENT;
      else if (s) cm = GL_SPECULAR;
      else if (e) cm = GL_EMISSION;
    }
    if (cm) {
      glEnable(GL_COLOR_MATERIAL);
      glColorMaterial(GL_FRONT_AND_BACK, cm);
    } else {
      glDisable(GL_COLOR_MATERIAL);
    }

    const auto mat = [](GLenum pname, const Color& c) {
      const GLfloat v[4] = {c.r,c.g,c.b,c.a};
      glMaterialfv(GL_FRONT_AND_BACK, pname, v);
    };
    mat(GL_DIFFUSE, material_.diffuse);
    mat(GL_AMBIENT, material_.ambient);
    mat(GL_SPECULAR, material_.specular);
    mat(GL_EMISSION, material_.emissive);
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, material_.power);

    glPushMatrix();
    glLoadIdentity();
    for (int i = 0; i < 8; ++i) {
      const GLenum gl_light = GL_LIGHT0 + i;
      if (!light_enabled_[i] || !light_valid_[i]) {
        glDisable(gl_light);
        continue;
      }
      glEnable(gl_light);
      const Light& l = lights_[i];
      const auto lc = [gl_light](GLenum pname, const Color& c) {
        const GLfloat v[4] = {c.r,c.g,c.b,c.a};
        glLightfv(gl_light, pname, v);
      };
      lc(GL_DIFFUSE, l.diffuse);
      lc(GL_SPECULAR, l.specular);
      lc(GL_AMBIENT, l.ambient);
      GLfloat pos[4] = {};
      if (l.type == 3) {
        pos[0] = -l.direction[0]; pos[1] = -l.direction[1];
        pos[2] = -l.direction[2]; pos[3] = 0;
      } else {
        pos[0] = l.position[0]; pos[1] = l.position[1];
        pos[2] = l.position[2]; pos[3] = 1;
      }
      glLightfv(gl_light, GL_POSITION, pos);
      glLightf(gl_light, GL_CONSTANT_ATTENUATION, l.attenuation0);
      glLightf(gl_light, GL_LINEAR_ATTENUATION, l.attenuation1);
      glLightf(gl_light, GL_QUADRATIC_ATTENUATION, l.attenuation2);
      if (l.type == 2) {
        const GLfloat dir[3] = {l.direction[0], l.direction[1], l.direction[2]};
        glLightfv(gl_light, GL_SPOT_DIRECTION, dir);
        glLightf(gl_light, GL_SPOT_CUTOFF,
                 std::clamp(l.phi * 90.0f / 3.14159265f, 0.0f, 90.0f));
      } else {
        glLightf(gl_light, GL_SPOT_CUTOFF, 180.0f);
      }
    }
    glPopMatrix();
  }

  void ApplyState() {
    glBindFramebuffer(GL_FRAMEBUFFER, back_fbo_);

    glViewport(GLint(viewport_.x),
               bb_h_ - GLint(viewport_.y + viewport_.height),
               GLsizei(viewport_.width), GLsizei(viewport_.height));
    glDepthRange(viewport_.min_z, viewport_.max_z);

    if (rs_[RS_SCISSORTESTENABLE]) {
      glEnable(GL_SCISSOR_TEST);
      glScissor(scissor_.left, bb_h_ - scissor_.bottom,
                std::max(0, scissor_.right - scissor_.left),
                std::max(0, scissor_.bottom - scissor_.top));
    } else glDisable(GL_SCISSOR_TEST);

    if (rs_[RS_ZENABLE]) glEnable(GL_DEPTH_TEST); else glDisable(GL_DEPTH_TEST);
    glDepthMask(rs_[RS_ZWRITEENABLE] ? GL_TRUE : GL_FALSE);
    glDepthFunc(Compare(rs_[RS_ZFUNC]));

    if (rs_[RS_ALPHABLENDENABLE]) glEnable(GL_BLEND); else glDisable(GL_BLEND);
    glBlendFunc(Blend(rs_[RS_SRCBLEND]), Blend(rs_[RS_DESTBLEND]));

    if (rs_[RS_ALPHATESTENABLE]) {
      glEnable(GL_ALPHA_TEST);
      glAlphaFunc(Compare(rs_[RS_ALPHAFUNC]),
                  GLfloat(rs_[RS_ALPHAREF] & 0xffu) / 255.0f);
    } else glDisable(GL_ALPHA_TEST);

    if (rs_[RS_CULLMODE] == 1) glDisable(GL_CULL_FACE);
    else {
      glEnable(GL_CULL_FACE);
      glFrontFace(GL_CCW);
      glCullFace(rs_[RS_CULLMODE] == 2 ? GL_BACK : GL_FRONT);
    }

    const GLenum poly = rs_[RS_FILLMODE] == 1 ? GL_POINT :
                        rs_[RS_FILLMODE] == 2 ? GL_LINE : GL_FILL;
    glPolygonMode(GL_FRONT_AND_BACK, poly);
    glShadeModel(rs_[RS_SHADEMODE] == 1 ? GL_FLAT : GL_SMOOTH);

    const float factor = FloatOf(rs_[RS_SLOPESCALEDEPTHBIAS]);
    const float units = FloatOf(rs_[RS_DEPTHBIAS]) * 16777216.0f;
    if (factor != 0 || units != 0) {
      glEnable(GL_POLYGON_OFFSET_FILL);
      glPolygonOffset(factor, units);
    } else glDisable(GL_POLYGON_OFFSET_FILL);

    const uint32_t mask = rs_[RS_COLORWRITEENABLE];
    glColorMask((mask & 1u) != 0, (mask & 2u) != 0,
                (mask & 4u) != 0, (mask & 8u) != 0);

    if (rs_[RS_STENCILENABLE]) {
      glEnable(GL_STENCIL_TEST);
      glStencilFunc(Compare(rs_[RS_STENCILFUNC]), GLint(rs_[RS_STENCILREF]),
                    GLuint(rs_[RS_STENCILMASK]));
      glStencilMask(GLuint(rs_[RS_STENCILWRITEMASK]));
      glStencilOp(Stencil(rs_[RS_STENCILFAIL]),
                  Stencil(rs_[RS_STENCILZFAIL]),
                  Stencil(rs_[RS_STENCILPASS]));
    } else glDisable(GL_STENCIL_TEST);

    if (rs_[RS_FOGENABLE]) {
      glEnable(GL_FOG);
      const uint32_t mode = rs_[RS_FOGVERTEXMODE];
      glFogi(GL_FOG_MODE, mode == 3 ? GL_LINEAR : mode == 2 ? GL_EXP2 : GL_EXP);
      GLfloat c[4]; Argb(rs_[RS_FOGCOLOR] | 0xff000000u, c);
      glFogfv(GL_FOG_COLOR, c);
      glFogf(GL_FOG_START, FloatOf(rs_[RS_FOGSTART]));
      glFogf(GL_FOG_END, FloatOf(rs_[RS_FOGEND]));
      glFogf(GL_FOG_DENSITY, FloatOf(rs_[RS_FOGDENSITY]));
    } else glDisable(GL_FOG);

    ApplyMatrices();
    ApplyLighting();

    glPushMatrix();
    glLoadIdentity();
    const uint32_t planes = rs_[RS_CLIPPLANEENABLE];
    for (int i = 0; i < 6; ++i) {
      const GLenum gl_plane = GL_CLIP_PLANE0 + i;
      if (planes & (1u << i)) {
        const GLdouble eq[4] = {
            clip_planes_[i][0], clip_planes_[i][1],
            clip_planes_[i][2], clip_planes_[i][3]};
        glClipPlane(gl_plane, eq);
        glEnable(gl_plane);
      } else glDisable(gl_plane);
    }
    glPopMatrix();

    for (uint32_t i = 0; i < 8; ++i) ApplyTextureStage(i);
    glActiveTexture(GL_TEXTURE0);
  }

  DeviceContext dc_{};
  WglHandle ctx_{};
  int out_w_{};
  int out_h_{};
  int bb_w_{};
  int bb_h_{};
  GLuint back_fbo_{};
  GLuint back_color_{};
  DepthId current_depth_{};

  TextureId next_texture_{1};
  DepthId next_depth_{1};
  std::unordered_map<TextureId, GlTexture> textures_;
  std::unordered_map<DepthId, GlDepth> depths_;

  std::array<uint32_t,256> rs_{};
  std::array<std::array<uint32_t,33>,8> tss_{};
  std::array<TextureId,8> bound_textures_{};
  std::array<float,16> world_{};
  std::array<float,16> view_{};
  std::array<float,16> projection_{};
  std::array<std::array<float,16>,8> texture_matrices_{};
  Viewport viewport_{};
  Rect scissor_{};
  Material material_{};
  std::array<Light,8> lights_{};
  std::array<bool,8> light_valid_{};
  std::array<bool,8> light_enabled_{};
  std::array<std::array<float,4>,8> clip_planes_{};

  std::vector<uint8_t> mapped_vertices_;
  std::vector<uint16_t> mapped_indices_;
  uint32_t mapped_vertex_count_{};
  uint32_t mapped_index_count_{};
  uint32_t mapped_stride_{};
};

}  // namespace

std::unique_ptr<Device> CreateGpuDevice(SDL_Window* window) {
  return std::make_unique<Ps5GlDevice>(window);
}

}  // namespace recomp::gfx
