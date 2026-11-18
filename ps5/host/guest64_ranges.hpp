// SPDX-License-Identifier: GPL-3.0-or-later
// Platform-independent validation of synthetic Win64 guest PE image layouts.
// Does NOT reserve or map host memory and deliberately rejects arithmetic
// overflow. Host-specific address-space reservation remains a separate gate.
#pragma once

#include <cstdint>
#include <limits>
#include <vector>

namespace refrozen::ps5 {

struct Guest64Range {
  std::uint64_t base{};
  std::uint64_t size{};

  // End is exclusive and must fit in uint64_t. This intentionally excludes
  // allocations ending at 2^64; PE image reservations never require that.
  [[nodiscard]] constexpr bool valid() const noexcept {
    return size != 0 && base <= std::numeric_limits<std::uint64_t>::max() - size;
  }

  [[nodiscard]] constexpr std::uint64_t end() const noexcept {
    return valid() ? base + size : 0;
  }

  [[nodiscard]] constexpr bool contains(std::uint64_t address,
                                        std::uint64_t length = 1) const noexcept {
    if (!valid() || length == 0 || length > size) return false;
    if (address < base || address >= end()) return false;
    return length <= end() - address;
  }
};

[[nodiscard]] constexpr bool overlaps(const Guest64Range& lhs,
                                      const Guest64Range& rhs) noexcept {
  return lhs.valid() && rhs.valid() && lhs.base < rhs.end() &&
         rhs.base < lhs.end();
}

enum class Guest64InsertResult { ok, invalid_range, overlap };

class Guest64Layout {
 public:
  [[nodiscard]] Guest64InsertResult add(Guest64Range range) {
    if (!range.valid()) return Guest64InsertResult::invalid_range;
    for (const auto& existing : images_) {
      if (overlaps(range, existing)) return Guest64InsertResult::overlap;
    }
    images_.push_back(range);
    return Guest64InsertResult::ok;
  }

  [[nodiscard]] const std::vector<Guest64Range>& images() const noexcept {
    return images_;
  }

 private:
  std::vector<Guest64Range> images_;
};

}  // namespace refrozen::ps5
