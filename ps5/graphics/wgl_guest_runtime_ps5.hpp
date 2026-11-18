// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "wgl_platform_contract.hpp"

#include <cstdint>

namespace refrozen::ps5::graphics {

using GuestGlProcResolver = std::uint64_t (*)(const char* name);

// Installed by the PS5 frontend before the translated Win64 entry point runs.
// The registry must outlive translated guest execution.
void InstallWglRegistry(WglRegistry* registry) noexcept;

// Optional resolver for generated GL thunks. It returns a guest-callable
// dispatcher address (for example rt_host_fn(...)), never a raw host GL pointer.
void InstallGuestGlProcResolver(GuestGlProcResolver resolver) noexcept;

}  // namespace refrozen::ps5::graphics
