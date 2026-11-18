// SPDX-License-Identifier: GPL-3.0-or-later
// Host-independent validation for 32-bit guest image reservations.
// These checks precede (and do not replace) the runtime's OS-specific
// virtual-memory reservation/commit implementation.
#pragma once

#include <cstdint>
#include <vector>

namespace refrozen::ps5 {

constexpr std::uint64_t kGuest32Limit = std::uint64_t{1} << 32;

struct Guest32Range {
  std::uint32_t base{};
  std::uint64_t size{};

  [[nodiscard]] constexpr std::uint64_t end() const noexcept {
    return static_cast<std::uint64_t>(base) + size;
  }

  [[nodiscard]] constexpr bool valid() const noexcept {
    return size != 0 && size <= kGuest32Limit && end() <= kGuest32Limit;
  }

  [[nodiscard]] constexpr bool contains(std::uint32_t addr,
                                        std::uint64_t length = 1) const noexcept {
    if (!valid() || length == 0 || length > size) return false;
    const std::uint64_t begin = addr;
    return begin >= base && begin < end() && length <= end() - begin;
  }
};

[[nodiscard]] constexpr bool overlaps(const Guest32Range& a,
                                      const Guest32Range& b) noexcept {
  if (!a.valid() || !b.valid()) return false;
  return static_cast<std::uint64_t>(a.base) < b.end() &&
         static_cast<std::uint64_t>(b.base) < a.end();
}

enum class InsertResult { ok, invalid_range, overlap };

// Checks a prospective PE image layout without creating or mapping host pages.
// The real reFrozen guest allocator remains the owner of virtual memory.
class Guest32Layout {
 public:
  [[nodiscard]] InsertResult add(Guest32Range range) {
    if (!range.valid()) return InsertResult::invalid_range;
    for (const auto& occupied : ranges_) {
      if (overlaps(range, occupied)) return InsertResult::overlap;
    }
    ranges_.push_back(range);
    return InsertResult::ok;
  }

  [[nodiscard]] const std::vector<Guest32Range>& ranges() const noexcept {
    return ranges_;
  }

 private:
  std::vector<Guest32Range> ranges_;
};

}  // namespace refrozen::ps5
