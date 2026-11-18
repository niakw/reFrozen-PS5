// SPDX-License-Identifier: GPL-3.0-or-later
// Host-independent WGL state/ownership contract. The platform backend may be
// PS5 EGL, a host test double, or another renderer implementation.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <mutex>

namespace refrozen::ps5::graphics {

using WglHandle = std::uint64_t;
using DeviceContext = std::uint64_t;
using BackendContext = std::uint64_t;

struct WglBackendOps {
  void* user{};
  BackendContext (*create_context)(void* user, BackendContext share,
                                   int profile_mask){};
  bool (*destroy_context)(void* user, BackendContext context){};
  bool (*make_current)(void* user, BackendContext context,
                       DeviceContext dc){};
  bool (*clear_current)(void* user){};
  bool (*swap_buffers)(void* user, DeviceContext dc){};
  void* (*get_proc_address)(void* user, const char* name){};
};

class WglRegistry {
 public:
  static constexpr std::size_t kMaxContexts = 64;
  static constexpr WglHandle kHandleBase = 0x474C0000ull;

  explicit WglRegistry(WglBackendOps ops) : ops_(ops) {}

  WglRegistry(const WglRegistry&) = delete;
  WglRegistry& operator=(const WglRegistry&) = delete;

  [[nodiscard]] WglHandle CreateContext(int profile_mask = 0,
                                        WglHandle share = 0);
  [[nodiscard]] bool DeleteContext(WglHandle context);
  [[nodiscard]] bool MakeCurrent(DeviceContext dc, WglHandle context);
  [[nodiscard]] bool ClearCurrent();

  [[nodiscard]] WglHandle CurrentContext() const noexcept;
  [[nodiscard]] DeviceContext CurrentDeviceContext() const noexcept;

  [[nodiscard]] bool SwapBuffers(DeviceContext dc);
  [[nodiscard]] void* GetProcAddress(const char* name);

  [[nodiscard]] std::size_t LiveContextCount() const;

 private:
  struct Slot {
    BackendContext backend{};
    std::uint32_t current_count{};
    int profile_mask{};
    bool alive{};
  };
  struct ThreadCurrent {
    const WglRegistry* registry{};
    std::size_t slot{kMaxContexts};
    DeviceContext dc{};
  };

  [[nodiscard]] static bool HandleToSlot(WglHandle handle,
                                         std::size_t* slot) noexcept;
  [[nodiscard]] bool ValidateOps() const noexcept;

  WglBackendOps ops_{};
  mutable std::mutex mutex_;
  std::array<Slot, kMaxContexts> slots_{};
  static thread_local ThreadCurrent current_;
};

}  // namespace refrozen::ps5::graphics
