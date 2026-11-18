// SPDX-License-Identifier: GPL-3.0-or-later
#include "wgl_platform_contract.hpp"

#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>

using refrozen::ps5::graphics::BackendContext;
using refrozen::ps5::graphics::DeviceContext;
using refrozen::ps5::graphics::WglBackendOps;
using refrozen::ps5::graphics::WglRegistry;

namespace {
struct FakeBackend {
  BackendContext next{100};
  BackendContext current{};
  DeviceContext dc{};
  int creates{};
  int destroys{};
  int swaps{};
  int clears{};
  int swap_interval{1};
  bool fail_make{};
  bool fail_destroy{};

  static BackendContext Create(void* user, BackendContext share, int profile) {
    auto& self = *static_cast<FakeBackend*>(user);
    assert(profile == 0 || profile == 1);
    assert(share == 0 || share >= 100);
    ++self.creates;
    return ++self.next;
  }
  static bool Destroy(void* user, BackendContext ctx) {
    auto& self = *static_cast<FakeBackend*>(user);
    if (self.fail_destroy) return false;
    assert(ctx >= 101);
    ++self.destroys;
    return true;
  }
  static bool MakeCurrent(void* user, BackendContext ctx, DeviceContext dc) {
    auto& self = *static_cast<FakeBackend*>(user);
    if (self.fail_make) return false;
    self.current = ctx;
    self.dc = dc;
    return true;
  }
  static bool Clear(void* user) {
    auto& self = *static_cast<FakeBackend*>(user);
    self.current = 0;
    self.dc = 0;
    ++self.clears;
    return true;
  }
  static bool Swap(void* user, DeviceContext dc) {
    auto& self = *static_cast<FakeBackend*>(user);
    if (!dc || dc != self.dc) return false;
    ++self.swaps;
    return true;
  }
  static bool SetSwapInterval(void* user, int interval) {
    auto& self = *static_cast<FakeBackend*>(user);
    self.swap_interval = interval;
    return true;
  }
  static void* Proc(void*, const char* name) {
    if (std::strcmp(name, "glExample") == 0) {
      return reinterpret_cast<void*>(static_cast<std::uintptr_t>(0x1234));
    }
    return nullptr;
  }
};

WglBackendOps Ops(FakeBackend* fake) {
  return {
      .user = fake,
      .create_context = FakeBackend::Create,
      .destroy_context = FakeBackend::Destroy,
      .make_current = FakeBackend::MakeCurrent,
      .clear_current = FakeBackend::Clear,
      .swap_buffers = FakeBackend::Swap,
      .set_swap_interval = FakeBackend::SetSwapInterval,
      .get_proc_address = FakeBackend::Proc,
  };
}
}  // namespace

int main() {
  FakeBackend fake;
  WglRegistry registry(Ops(&fake));

  assert(registry.LiveContextCount() == 0);
  assert(registry.CurrentContext() == 0);
  assert(registry.GetProcAddress("glExample") == nullptr);
  assert(!registry.MakeCurrent(0, WglRegistry::kHandleBase + 1));

  const auto a = registry.CreateContext(0);
  assert(a == WglRegistry::kHandleBase + 1);
  const auto b = registry.CreateContext(1, a);
  assert(b == WglRegistry::kHandleBase + 2);
  assert(fake.creates == 2);
  assert(registry.LiveContextCount() == 2);

  assert(registry.MakeCurrent(0xABC, a));
  assert(registry.CurrentContext() == a);
  assert(registry.CurrentDeviceContext() == 0xABC);
  assert(registry.GetProcAddress("glExample") ==
         reinterpret_cast<void*>(static_cast<std::uintptr_t>(0x1234)));
  assert(registry.SwapBuffers(0xABC));
  assert(!registry.SwapBuffers(0xABD));
  assert(fake.swaps == 1);
  assert(registry.SetSwapInterval(0));
  assert(fake.swap_interval == 0);

  // A current context cannot be destroyed.
  assert(!registry.DeleteContext(a));

  // A failed switch must leave the old WGL state current.
  fake.fail_make = true;
  assert(!registry.MakeCurrent(0xDEF, b));
  assert(registry.CurrentContext() == a);
  assert(registry.CurrentDeviceContext() == 0xABC);
  fake.fail_make = false;

  assert(registry.MakeCurrent(0xDEF, b));
  assert(registry.CurrentContext() == b);
  assert(registry.CurrentDeviceContext() == 0xDEF);

  assert(registry.ClearCurrent());
  assert(registry.CurrentContext() == 0);
  assert(registry.CurrentDeviceContext() == 0);
  assert(fake.clears == 1);
  assert(!registry.SetSwapInterval(1));

  fake.fail_destroy = true;
  assert(!registry.DeleteContext(a));
  assert(registry.LiveContextCount() == 2);
  fake.fail_destroy = false;
  assert(registry.DeleteContext(a));
  assert(registry.DeleteContext(b));
  assert(fake.destroys == 2);
  assert(registry.LiveContextCount() == 0);

  std::cout << "wgl_platform_contract: PASS\n";
}
