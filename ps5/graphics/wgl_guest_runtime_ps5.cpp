// SPDX-License-Identifier: GPL-3.0-or-later
#include "wgl_guest_runtime_ps5.hpp"

extern "C" {
#include "rt.h"
}

#include <atomic>
#include <cstdint>
#include <cstring>

namespace refrozen::ps5::graphics {
namespace {

std::atomic<WglRegistry*> g_registry{nullptr};
std::atomic<GuestGlProcResolver> g_gl_resolver{nullptr};
std::atomic<GuestGlProcObserver> g_gl_observer{nullptr};
std::atomic<int> g_swap_interval{1};

WglRegistry* Registry() noexcept {
  return g_registry.load(std::memory_order_acquire);
}


constexpr char kWglExtensions[] =
    "WGL_ARB_extensions_string WGL_EXT_extensions_string "
    "WGL_ARB_pixel_format WGL_ARB_create_context "
    "WGL_ARB_create_context_profile WGL_EXT_swap_control "
    "WGL_ARB_framebuffer_sRGB WGL_EXT_framebuffer_sRGB";

int PixelFormatAttribute(int attribute) noexcept {
  switch (attribute) {
    case 0x2000: return 1;       // WGL_NUMBER_PIXEL_FORMATS_ARB
    case 0x2001:                // WGL_DRAW_TO_WINDOW_ARB
    case 0x2010:                // WGL_SUPPORT_OPENGL_ARB
    case 0x2011: return 1;       // WGL_DOUBLE_BUFFER_ARB
    case 0x2003: return 0x2027;  // WGL_FULL_ACCELERATION_ARB
    case 0x2007: return 0x2028;  // WGL_SWAP_EXCHANGE_ARB
    case 0x2013: return 0x202B;  // WGL_TYPE_RGBA_ARB
    case 0x2014: return 32;      // WGL_COLOR_BITS_ARB
    case 0x2015:                 // RED_BITS
    case 0x2017:                 // GREEN_BITS
    case 0x2019:                 // BLUE_BITS
    case 0x201B: return 8;       // ALPHA_BITS
    case 0x2016: return 16;      // RED_SHIFT
    case 0x2018: return 8;       // GREEN_SHIFT
    case 0x201A: return 0;       // BLUE_SHIFT
    case 0x201C: return 24;      // ALPHA_SHIFT
    case 0x2022: return 24;      // DEPTH_BITS
    case 0x2023: return 8;       // STENCIL_BITS
    case 0x20A9: return 1;       // FRAMEBUFFER_SRGB_CAPABLE_ARB
    default: return 0;
  }
}

void WglGetExtensionsStringARB(CPU* c) { RET(G(kWglExtensions)); }
void WglGetExtensionsStringEXT(CPU* c) { RET(G(kWglExtensions)); }

void WglChoosePixelFormatARB(CPU* c) {
  const std::uint64_t formats = AN(4);
  const std::uint64_t count = AN(5);
  if (static_cast<std::uint32_t>(A3) && formats) wr32(formats, 1);
  if (count) wr32(count, 1);
  RET(1);
}

void WglGetPixelFormatAttribivARB(CPU* c) {
  const auto count = static_cast<std::uint32_t>(A3);
  const std::uint64_t attributes = AN(4);
  const std::uint64_t values = AN(5);
  if ((!attributes || !values) && count) {
    RET(0);
    return;
  }
  for (std::uint32_t i = 0; i < count; ++i) {
    const int attribute = static_cast<int>(rd32(attributes + 4ull * i));
    wr32(values + 4ull * i,
         static_cast<std::uint32_t>(PixelFormatAttribute(attribute)));
  }
  RET(1);
}

void WglGetPixelFormatAttribfvARB(CPU* c) {
  const auto count = static_cast<std::uint32_t>(A3);
  const std::uint64_t attributes = AN(4);
  const std::uint64_t values = AN(5);
  if ((!attributes || !values) && count) {
    RET(0);
    return;
  }
  for (std::uint32_t i = 0; i < count; ++i) {
    const int attribute = static_cast<int>(rd32(attributes + 4ull * i));
    const float value = static_cast<float>(PixelFormatAttribute(attribute));
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    wr32(values + 4ull * i, bits);
  }
  RET(1);
}

void WglCreateContextAttribsARB(CPU* c) {
  WglRegistry* registry = Registry();
  if (!registry) {
    RET(0);
    return;
  }

  const WglHandle share = A1;
  std::uint64_t attributes = A2;
  int major = 0;
  int minor = 0;
  int profile = 0;
  for (std::size_t guard = 0; attributes && guard < 64; ++guard, attributes += 8) {
    const std::uint32_t key = rd32(attributes);
    if (!key) break;
    const int value = static_cast<int>(rd32(attributes + 4));
    if (key == 0x2091) major = value;       // WGL_CONTEXT_MAJOR_VERSION_ARB
    else if (key == 0x2092) minor = value;  // WGL_CONTEXT_MINOR_VERSION_ARB
    else if (key == 0x9126) profile = value; // WGL_CONTEXT_PROFILE_MASK_ARB
  }
  if (!profile) {
    profile = (major > 3 || (major == 3 && minor >= 2))
                  ? kWglContextCoreProfileBit
                  : kWglContextCompatibilityProfileBit;
  }
  RET(registry->CreateContext(profile, share));
}

void WglSwapIntervalEXT(CPU* c) {
  WglRegistry* registry = Registry();
  const int interval = static_cast<int>(static_cast<std::int32_t>(A0));
  if (!registry || !registry->SetSwapInterval(interval)) {
    RET(0);
    return;
  }
  g_swap_interval.store(interval, std::memory_order_release);
  RET(1);
}

void WglGetSwapIntervalEXT(CPU* c) {
  RET(g_swap_interval.load(std::memory_order_acquire));
}

struct GuestProc {
  const char* name;
  gfn function;
};

constexpr GuestProc kWglProcs[] = {
    {"wglGetExtensionsStringARB", WglGetExtensionsStringARB},
    {"wglGetExtensionsStringEXT", WglGetExtensionsStringEXT},
    {"wglChoosePixelFormatARB", WglChoosePixelFormatARB},
    {"wglGetPixelFormatAttribivARB", WglGetPixelFormatAttribivARB},
    {"wglGetPixelFormatAttribfvARB", WglGetPixelFormatAttribfvARB},
    {"wglCreateContextAttribsARB", WglCreateContextAttribsARB},
    {"wglSwapIntervalEXT", WglSwapIntervalEXT},
    {"wglGetSwapIntervalEXT", WglGetSwapIntervalEXT},
};

}  // namespace

WglRegistry* InstalledWglRegistry() noexcept {
  return Registry();
}

std::uint64_t ResolveGuestWglProc(const char* name) {
  if (!name || !*name) return 0;
  if (const auto observer = g_gl_observer.load(std::memory_order_acquire))
    observer(name);
  for (const auto& proc : kWglProcs) {
    if (std::strcmp(proc.name, name) == 0) {
      return rt_host_fn(proc.function, proc.name);
    }
  }
  const auto resolver = g_gl_resolver.load(std::memory_order_acquire);
  return resolver ? resolver(name) : 0;
}

void InstallWglRegistry(WglRegistry* registry) noexcept {
  g_registry.store(registry, std::memory_order_release);
}

void InstallGuestGlProcResolver(GuestGlProcResolver resolver) noexcept {
  g_gl_resolver.store(resolver, std::memory_order_release);
}

void InstallGuestGlProcObserver(GuestGlProcObserver observer) noexcept {
  g_gl_observer.store(observer, std::memory_order_release);
}

}  // namespace refrozen::ps5::graphics

extern "C" {

void I_opengl32_dll_wglCreateContext(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  RET(registry ? registry->CreateContext(
                     refrozen::ps5::graphics::kWglContextCompatibilityProfileBit)
               : 0);
}

void I_opengl32_dll_wglDeleteContext(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  if (!registry) {
    RET(0);
    return;
  }
  const auto handle = static_cast<refrozen::ps5::graphics::WglHandle>(A0);
  if (registry->CurrentContext() == handle && !registry->ClearCurrent()) {
    RET(0);
    return;
  }
  RET(registry->DeleteContext(handle) ? 1 : 0);
}

void I_opengl32_dll_wglMakeCurrent(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  if (!registry) {
    RET(0);
    return;
  }
  if (!A1) {
    RET(registry->ClearCurrent() ? 1 : 0);
    return;
  }
  if (!registry->MakeCurrent(A0, A1)) {
    set_last_error(2000);
    RET(0);
    return;
  }
  RET(1);
}

void I_opengl32_dll_wglGetCurrentContext(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  RET(registry ? registry->CurrentContext() : 0);
}

void I_opengl32_dll_wglGetCurrentDC(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  RET(registry ? registry->CurrentDeviceContext() : 0);
}

void I_opengl32_dll_wglShareLists(CPU* c) {
  // The PS5 EGL backend creates every context in one share group. Keep this
  // successful no-op behavior aligned with the existing NightSight runtime.
  RET(refrozen::ps5::graphics::InstalledWglRegistry() ? 1 : 0);
}

void I_gdi32_dll_SwapBuffers(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  RET(registry && registry->SwapBuffers(A0) ? 1 : 0);
}

void I_opengl32_dll_wglSwapBuffers(CPU* c) {
  I_gdi32_dll_SwapBuffers(c);
}

void I_opengl32_dll_wglSwapLayerBuffers(CPU* c) {
  I_gdi32_dll_SwapBuffers(c);
}

void I_gdi32_dll_ChoosePixelFormat(CPU* c) { RET(1); }
void I_gdi32_dll_SetPixelFormat(CPU* c) { RET(1); }
void I_gdi32_dll_GetPixelFormat(CPU* c) { RET(1); }

void I_gdi32_dll_DescribePixelFormat(CPU* c) {
  const std::uint64_t p = A3;
  if (p && static_cast<std::uint32_t>(A2) >= 40) {
    auto* bytes = static_cast<std::uint8_t*>(PTR(p));
    std::memset(bytes, 0, 40);
    wr16(p, 40);
    wr16(p + 2, 1);
    wr32(p + 4, 0x4u | 0x20u | 0x1u);
    bytes[8] = 0;
    bytes[9] = 32;
    bytes[10] = 8; bytes[11] = 16;
    bytes[12] = 8; bytes[13] = 8;
    bytes[14] = 8; bytes[15] = 0;
    bytes[16] = 8; bytes[17] = 24;
    bytes[23] = 24;
    bytes[24] = 8;
  }
  RET(1);
}

void I_opengl32_dll_wglChoosePixelFormat(CPU* c) {
  I_gdi32_dll_ChoosePixelFormat(c);
}
void I_opengl32_dll_wglSetPixelFormat(CPU* c) {
  I_gdi32_dll_SetPixelFormat(c);
}
void I_opengl32_dll_wglDescribePixelFormat(CPU* c) {
  I_gdi32_dll_DescribePixelFormat(c);
}

void I_opengl32_dll_wglGetProcAddress(CPU* c) {
  auto* registry = refrozen::ps5::graphics::InstalledWglRegistry();
  const char* name = static_cast<const char*>(PTR(A0));
  if (!registry || !registry->CurrentContext() || !name || !*name) {
    RET(0);
    return;
  }

  RET(refrozen::ps5::graphics::ResolveGuestWglProc(name));
}

}  // extern "C"
