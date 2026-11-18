// SPDX-License-Identifier: GPL-3.0-or-later
#include "wgl_platform_contract.hpp"

#include <cstring>

namespace refrozen::ps5::graphics {

thread_local WglRegistry::ThreadCurrent WglRegistry::current_{};

bool WglRegistry::HandleToSlot(WglHandle handle, std::size_t* slot) noexcept {
  if (handle <= kHandleBase || handle > kHandleBase + kMaxContexts) return false;
  *slot = static_cast<std::size_t>(handle - kHandleBase - 1);
  return true;
}

bool WglRegistry::ValidateOps() const noexcept {
  return ops_.create_context && ops_.destroy_context && ops_.make_current &&
         ops_.clear_current && ops_.swap_buffers && ops_.get_proc_address;
}

WglHandle WglRegistry::CreateContext(int profile_mask, WglHandle share) {
  if (!ValidateOps()) return 0;
  std::lock_guard lock(mutex_);

  BackendContext share_backend = 0;
  if (share) {
    std::size_t share_slot = 0;
    if (!HandleToSlot(share, &share_slot) || !slots_[share_slot].alive) return 0;
    share_backend = slots_[share_slot].backend;
  }

  std::size_t free_slot = kMaxContexts;
  for (std::size_t i = 0; i < kMaxContexts; ++i) {
    if (!slots_[i].alive) {
      free_slot = i;
      break;
    }
  }
  if (free_slot == kMaxContexts) return 0;

  const BackendContext backend =
      ops_.create_context(ops_.user, share_backend, profile_mask);
  if (!backend) return 0;

  slots_[free_slot] = {
      .backend = backend,
      .current_count = 0,
      .profile_mask = profile_mask,
      .alive = true,
  };
  return kHandleBase + free_slot + 1;
}

bool WglRegistry::DeleteContext(WglHandle context) {
  std::size_t slot = 0;
  if (!HandleToSlot(context, &slot) || !ValidateOps()) return false;

  std::lock_guard lock(mutex_);
  Slot& item = slots_[slot];
  if (!item.alive || item.current_count != 0) return false;
  if (!ops_.destroy_context(ops_.user, item.backend)) return false;
  item = {};
  return true;
}

bool WglRegistry::MakeCurrent(DeviceContext dc, WglHandle context) {
  if (!context) return dc == 0 && ClearCurrent();
  if (!dc || !ValidateOps()) return false;

  std::size_t next_slot = 0;
  if (!HandleToSlot(context, &next_slot)) return false;

  std::lock_guard lock(mutex_);
  Slot& next = slots_[next_slot];
  if (!next.alive) return false;

  if (!ops_.make_current(ops_.user, next.backend, dc)) return false;

  if (current_.registry == this && current_.slot < kMaxContexts) {
    Slot& previous = slots_[current_.slot];
    if (previous.alive && previous.current_count) --previous.current_count;
  }
  ++next.current_count;
  current_ = {.registry = this, .slot = next_slot, .dc = dc};
  return true;
}

bool WglRegistry::ClearCurrent() {
  if (!ValidateOps()) return false;
  std::lock_guard lock(mutex_);

  if (current_.registry != this || current_.slot >= kMaxContexts) {
    return ops_.clear_current(ops_.user);
  }
  if (!ops_.clear_current(ops_.user)) return false;

  Slot& previous = slots_[current_.slot];
  if (previous.alive && previous.current_count) --previous.current_count;
  current_ = {};
  return true;
}

WglHandle WglRegistry::CurrentContext() const noexcept {
  if (current_.registry != this || current_.slot >= kMaxContexts) return 0;
  return kHandleBase + current_.slot + 1;
}

DeviceContext WglRegistry::CurrentDeviceContext() const noexcept {
  return current_.registry == this ? current_.dc : 0;
}

bool WglRegistry::SwapBuffers(DeviceContext dc) {
  if (!dc || current_.registry != this || current_.dc != dc || !ValidateOps()) {
    return false;
  }
  return ops_.swap_buffers(ops_.user, dc);
}

void* WglRegistry::GetProcAddress(const char* name) {
  if (!name || !*name || current_.registry != this ||
      current_.slot >= kMaxContexts || !ValidateOps()) {
    return nullptr;
  }
  return ops_.get_proc_address(ops_.user, name);
}

std::size_t WglRegistry::LiveContextCount() const {
  std::lock_guard lock(mutex_);
  std::size_t count = 0;
  for (const auto& slot : slots_) count += slot.alive ? 1u : 0u;
  return count;
}

}  // namespace refrozen::ps5::graphics
