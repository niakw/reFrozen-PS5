// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 ABI probe: translated synthetic Win64 guest -> WGL imports -> WglRegistry
// -> deterministic backend. No OpenGL driver or Warcraft data is present.
#include "guest_image_mapping_ps5.hpp"
#include "pe_image_materializer.hpp"
#include "wgl_guest_runtime_ps5.hpp"
#include "wgl_platform_contract.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <span>
#include <string_view>

extern "C" {
#include "rt.h"
extern const unsigned char g_refrozen_synthetic_wgl_pe[];
extern const std::size_t g_refrozen_synthetic_wgl_pe_size;
}

namespace {
using namespace refrozen::ps5::graphics;

constexpr std::size_t kMaxSections = 16;
constexpr DeviceContext kDeviceContext = UINT64_C(0x1111);
constexpr BackendContext kBackendContext = UINT64_C(0xBEEF);
constexpr std::uint64_t kGuestGlProc = UINT64_C(0x7ff100001000);
constexpr std::array<std::string_view, 4> kImports = {
    "opengl32.dll!wglCreateContext",
    "opengl32.dll!wglMakeCurrent",
    "opengl32.dll!wglGetProcAddress",
    "opengl32.dll!wglSwapBuffers",
};

struct BackendState {
  int create_calls{};
  int destroy_calls{};
  int make_current_calls{};
  int clear_calls{};
  int swap_calls{};
  int swap_interval_calls{};
  int proc_calls{};
  bool args_ok{true};
};

BackendContext CreateContext(void* user, BackendContext share, int profile) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.create_calls;
  s.args_ok &= share == 0;
  s.args_ok &= profile == kWglContextCompatibilityProfileBit;
  return kBackendContext;
}

bool DestroyContext(void* user, BackendContext context) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.destroy_calls;
  s.args_ok &= context == kBackendContext;
  return context == kBackendContext;
}

bool MakeCurrent(void* user, BackendContext context, DeviceContext dc) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.make_current_calls;
  s.args_ok &= context == kBackendContext && dc == kDeviceContext;
  return context == kBackendContext && dc == kDeviceContext;
}

bool ClearCurrent(void* user) {
  ++static_cast<BackendState*>(user)->clear_calls;
  return true;
}

bool SwapBuffers(void* user, DeviceContext dc) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.swap_calls;
  s.args_ok &= dc == kDeviceContext;
  return dc == kDeviceContext;
}

bool SetSwapInterval(void* user, int interval) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.swap_interval_calls;
  s.args_ok &= interval >= 0;
  return interval >= 0;
}

void* BackendGetProcAddress(void* user, const char* name) {
  auto& s = *static_cast<BackendState*>(user);
  ++s.proc_calls;
  (void)name;
  return nullptr;
}

std::uint64_t ResolveGuestGlProc(const char* name) {
  return name && std::strcmp(name, "glGetString") == 0 ? kGuestGlProc : 0;
}

int Fail(const char* stage, int detail = 0) {
  std::fprintf(stderr,
               "REFROZEN_PS5_WGL_CHAIN pass=0 stage=%s detail=%d\n",
               stage, detail);
  return 1;
}

bool ReadU32(std::size_t offset, std::uint32_t* out) {
  if (!out || offset > g_refrozen_synthetic_wgl_pe_size ||
      sizeof(*out) > g_refrozen_synthetic_wgl_pe_size - offset) {
    return false;
  }
  std::memcpy(out, g_refrozen_synthetic_wgl_pe + offset, sizeof(*out));
  return true;
}

bool ReadHeadersSize(std::size_t* out) {
  if (!out || g_refrozen_synthetic_wgl_pe_size < 0x40 ||
      g_refrozen_synthetic_wgl_pe[0] != 'M' ||
      g_refrozen_synthetic_wgl_pe[1] != 'Z') {
    return false;
  }
  std::uint32_t pe_offset = 0;
  if (!ReadU32(0x3c, &pe_offset) ||
      static_cast<std::size_t>(pe_offset) + 24 >
          g_refrozen_synthetic_wgl_pe_size) {
    return false;
  }
  const auto pe = static_cast<std::size_t>(pe_offset);
  if (std::memcmp(g_refrozen_synthetic_wgl_pe + pe, "PE\0\0", 4) != 0) {
    return false;
  }
  std::uint32_t headers = 0;
  if (!ReadU32(pe + 24 + 60, &headers) || !headers) return false;
  *out = headers;
  return true;
}

gfn FindGeneratedFunction(std::uint64_t address) {
  int lo = 0;
  int hi = ngfuncs - 1;
  while (lo <= hi) {
    const int middle = lo + (hi - lo) / 2;
    if (gfuncs[middle].addr == address) return gfuncs[middle].fn;
    if (gfuncs[middle].addr < address)
      lo = middle + 1;
    else
      hi = middle - 1;
  }
  return nullptr;
}

const GSection* FindSection(std::string_view name) {
  for (int i = 0; i < ngsections; ++i) {
    if (gsections[i].name && name == gsections[i].name) return &gsections[i];
  }
  return nullptr;
}

std::uint64_t g_unimplemented_calls = 0;
std::uint32_t g_last_error = 0;

}  // namespace

extern "C" {
int rt_strict = 0;

void set_last_error(std::uint32_t error) { g_last_error = error; }
std::uint32_t get_last_error(void) { return g_last_error; }

std::uint64_t rt_host_fn(gfn function, const char* name) {
  (void)function;
  (void)name;
  return HOSTFN_BASE + 0x1000;
}

void unimpl_import(CPU* c, const char* name) {
  (void)name;
  ++g_unimplemented_calls;
  c->rax = 0;
}
}

int main() {
  if (!gimage_base || !gimage_size || !gentry || ngfuncs <= 0 ||
      ngsections <= 0 || ngsections > static_cast<int>(kMaxSections) ||
      ngimports != static_cast<int>(kImports.size())) {
    return Fail("generated-tables");
  }
  for (std::size_t i = 0; i < kImports.size(); ++i) {
    if (!gimports[i].name || kImports[i] != gimports[i].name) {
      return Fail("import-order", static_cast<int>(i));
    }
  }

  const auto mapping =
      refrozen::ps5::MapGuestImagePs5(gimage_base, gimage_size);
  if (!mapping.ok()) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WGL_CHAIN pass=0 stage=map status=%d abort=%d\n",
                 static_cast<int>(mapping.status),
                 mapping.requires_process_abort() ? 1 : 0);
    return mapping.requires_process_abort() ? 2 : 1;
  }

  std::array<refrozen::ps5::PeSectionCopy, kMaxSections> sections{};
  for (int i = 0; i < ngsections; ++i) {
    const auto& generated = gsections[i];
    sections[static_cast<std::size_t>(i)] = {
        generated.name ? std::string_view(generated.name) : std::string_view{},
        generated.va, generated.vsize, generated.fo, generated.fsize,
        generated.flags};
  }

  std::size_t headers_size = 0;
  if (!ReadHeadersSize(&headers_size)) {
    (void)refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return Fail("pe-headers");
  }
  const refrozen::ps5::PeImageCopyLayout layout{
      gimage_base, gimage_size, headers_size,
      std::span<const refrozen::ps5::PeSectionCopy>(
          sections.data(), static_cast<std::size_t>(ngsections))};
  auto destination = std::span<std::uint8_t>(
      reinterpret_cast<std::uint8_t*>(
          static_cast<std::uintptr_t>(gimage_base)),
      static_cast<std::size_t>(gimage_size));
  const auto source = std::span<const std::uint8_t>(
      g_refrozen_synthetic_wgl_pe, g_refrozen_synthetic_wgl_pe_size);
  const auto loaded =
      refrozen::ps5::MaterializePeImage(source, destination, layout);
  if (!loaded.ok()) {
    (void)refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return Fail("materialize", static_cast<int>(loaded.status));
  }

  const auto* data_section = FindSection(".data");
  gfn const entry = FindGeneratedFunction(gentry);
  if (!data_section || data_section->vsize < 24 || !entry) {
    (void)refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return Fail("dispatch");
  }
  auto* data = reinterpret_cast<volatile std::uint64_t*>(
      static_cast<std::uintptr_t>(data_section->va));
  if (data[0] || data[1] || data[2]) {
    (void)refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return Fail("initial-data");
  }

  BackendState backend{};
  WglBackendOps ops{
      .user = &backend,
      .create_context = CreateContext,
      .destroy_context = DestroyContext,
      .make_current = MakeCurrent,
      .clear_current = ClearCurrent,
      .swap_buffers = SwapBuffers,
      .set_swap_interval = SetSwapInterval,
      .get_proc_address = BackendGetProcAddress,
  };
  WglRegistry registry(ops);
  InstallWglRegistry(&registry);
  InstallGuestGlProcResolver(ResolveGuestGlProc);

  const std::uint64_t initial_rsp =
      gimage_base + static_cast<std::uint64_t>(mapping.backing.mapped_size) -
      0x100;
  if (initial_rsp <= gimage_base + gimage_size) {
    InstallGuestGlProcResolver(nullptr);
    InstallWglRegistry(nullptr);
    (void)refrozen::ps5::ReleaseGuestImagePs5(mapping);
    return Fail("stack-range");
  }

  g_unimplemented_calls = 0;
  g_last_error = 0;
  CPU state{};
  state.rsp = initial_rsp;
  entry(&state);

  const WglHandle expected_handle = WglRegistry::kHandleBase + 1;
  const bool guest_ok =
      data[0] == expected_handle && data[1] == kGuestGlProc && data[2] == 1 &&
      state.rax == 1 && state.rsp == initial_rsp + 8 &&
      state.fn == gentry && g_unimplemented_calls == 0 && g_last_error == 0;
  const bool backend_ok =
      backend.args_ok && backend.create_calls == 1 &&
      backend.make_current_calls == 1 && backend.swap_calls == 1 &&
      registry.CurrentContext() == expected_handle &&
      registry.CurrentDeviceContext() == kDeviceContext &&
      registry.LiveContextCount() == 1;

  const bool cleanup_ok =
      registry.ClearCurrent() && registry.DeleteContext(expected_handle) &&
      backend.clear_calls == 1 && backend.destroy_calls == 1 &&
      registry.LiveContextCount() == 0;
  InstallGuestGlProcResolver(nullptr);
  InstallWglRegistry(nullptr);

  const auto released = refrozen::ps5::ReleaseGuestImagePs5(mapping);
  if (released.status != refrozen::ps5::DirectBackingReleaseStatus::ok) {
    return 2;
  }
  if (!guest_ok || !backend_ok || !cleanup_ok) {
    std::fprintf(stderr,
                 "REFROZEN_PS5_WGL_CHAIN pass=0 stage=execute "
                 "ctx=%llx proc=%llx swap=%llu create=%d current=%d "
                 "swaps=%d clear=%d destroy=%d fallback=%llu last=%u\n",
                 static_cast<unsigned long long>(data[0]),
                 static_cast<unsigned long long>(data[1]),
                 static_cast<unsigned long long>(data[2]),
                 backend.create_calls, backend.make_current_calls,
                 backend.swap_calls, backend.clear_calls, backend.destroy_calls,
                 static_cast<unsigned long long>(g_unimplemented_calls),
                 static_cast<unsigned>(g_last_error));
    return 1;
  }

  std::fprintf(stderr,
               "REFROZEN_PS5_WGL_CHAIN pass=1 entry=%llx imports=%d "
               "ctx=%llx proc=%llx swap=%llu backend_create=%d backend_swap=%d\n",
               static_cast<unsigned long long>(gentry), ngimports,
               static_cast<unsigned long long>(expected_handle),
               static_cast<unsigned long long>(kGuestGlProc),
               static_cast<unsigned long long>(1), backend.create_calls,
               backend.swap_calls);
  return 0;
}
