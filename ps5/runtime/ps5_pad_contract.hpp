// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Minimal independently-authored PS5 pad interoperability contract.
// Layout is intentionally kept compatible with the native scePad sample
// consumed by the Encore PS5 frontend; no proprietary SDK header is bundled.

#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace refrozen::ps5::pad {

using ButtonMask = std::uint32_t;
inline constexpr std::int32_t kPortTypeStandard = 0;
inline constexpr std::uint32_t kSampleSize = 120;

inline constexpr ButtonMask kButtonL3       = 0x00000002U;
inline constexpr ButtonMask kButtonR3       = 0x00000004U;
inline constexpr ButtonMask kButtonOptions  = 0x00000008U;
inline constexpr ButtonMask kButtonUp       = 0x00000010U;
inline constexpr ButtonMask kButtonRight    = 0x00000020U;
inline constexpr ButtonMask kButtonDown     = 0x00000040U;
inline constexpr ButtonMask kButtonLeft     = 0x00000080U;
inline constexpr ButtonMask kButtonL2       = 0x00000100U;
inline constexpr ButtonMask kButtonR2       = 0x00000200U;
inline constexpr ButtonMask kButtonL1       = 0x00000400U;
inline constexpr ButtonMask kButtonR1       = 0x00000800U;
inline constexpr ButtonMask kButtonTriangle = 0x00001000U;
inline constexpr ButtonMask kButtonCircle   = 0x00002000U;
inline constexpr ButtonMask kButtonCross    = 0x00004000U;
inline constexpr ButtonMask kButtonSquare   = 0x00008000U;
inline constexpr ButtonMask kButtonTouchPad = 0x00100000U;
inline constexpr ButtonMask kButtonIntercepted = 0x80000000U;

struct Stick { std::uint8_t x, y; };
struct AnalogButtons {
  std::uint8_t l2, r2;
  std::array<std::uint8_t, 2> reserved;
};
struct Quaternion { float x, y, z, w; };
struct Vector3 { float x, y, z; };
struct Touch {
  std::uint16_t x, y;
  std::uint8_t id;
  std::array<std::uint8_t, 3> reserved;
};
struct TouchData {
  std::uint8_t count;
  std::array<std::uint8_t, 7> reserved;
  std::array<Touch, 2> points;
};
struct ExtensionData {
  std::uint32_t unit_id;
  std::uint8_t reserved;
  std::uint8_t length;
  std::array<std::uint8_t, 10> data;
};
struct Data {
  ButtonMask buttons;
  Stick left_stick;
  Stick right_stick;
  AnalogButtons triggers;
  Quaternion orientation;
  Vector3 acceleration;
  Vector3 angular_velocity;
  TouchData touch;
  std::int32_t connected;
  std::uint64_t timestamp_us;
  ExtensionData extension;
  std::uint8_t connected_count;
  std::array<std::uint8_t, 2> reserved;
  std::uint8_t device_unique_data_length;
  std::array<std::uint8_t, 12> device_unique_data;
};

[[nodiscard]] constexpr bool usable(const Data& sample) noexcept {
  return sample.connected != 0 &&
         (sample.buttons & kButtonIntercepted) == 0;
}

static_assert(sizeof(Data) == kSampleSize);
static_assert(offsetof(Data, connected) == 0x4c);
static_assert(offsetof(Data, timestamp_us) == 0x50);
static_assert(std::is_standard_layout_v<Data>);
static_assert(std::is_trivially_copyable_v<Data>);

}  // namespace refrozen::ps5::pad

extern "C" {
std::int32_t sceUserServiceInitialize(void* parameters);
std::int32_t sceUserServiceGetForegroundUser(std::int32_t* user_id);
std::int32_t sceUserServiceTerminate();
std::int32_t scePadInit();
std::int32_t scePadOpen(std::int32_t user_id, std::int32_t port_type,
                        std::int32_t index, const void* parameters);
std::int32_t scePadClose(std::int32_t handle);
std::int32_t scePadReadState(std::int32_t handle,
                             refrozen::ps5::pad::Data* data);
}
