// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest32_ranges.hpp"

#include <cassert>
#include <cstdint>
#include <iostream>

using refrozen::ps5::Guest32Layout;
using refrozen::ps5::Guest32Range;
using refrozen::ps5::InsertResult;
using refrozen::ps5::kGuest32Limit;
using refrozen::ps5::overlaps;

static_assert(sizeof(std::uint32_t) == 4);
static_assert(kGuest32Limit == 0x100000000ULL);
static_assert(Guest32Range{0xffff0000U, 0x10000U}.valid());
static_assert(!Guest32Range{0xffff0000U, 0x10001U}.valid());
static_assert(!Guest32Range{0, 0}.valid());
static_assert(Guest32Range{0, 0x100000000ULL}.valid());
static_assert(Guest32Range{0, 0x100000000ULL}.contains(0xffffffffU));
static_assert(!Guest32Range{0x1000U, 0x1000U}.contains(0x1fffU, 2));
static_assert(overlaps({0x1000U, 0x1000U}, {0x1fffU, 2}));
static_assert(!overlaps({0x1000U, 0x1000U}, {0x2000U, 0x1000U}));

int main() {
  Guest32Layout layout;
  // Synthetic, publicly distributable 32-bit PE image addresses.
  assert(layout.add({0x00400000U, 0x00800000U}) == InsertResult::ok);
  assert(layout.add({0x6f000000U, 0x01000000U}) == InsertResult::ok);
  assert(layout.add({0x70000000U, 0x00020000U}) == InsertResult::ok);
  assert(layout.ranges().size() == 3);
  assert(layout.add({0x6ffffff0U, 0x40U}) == InsertResult::overlap);
  assert(layout.add({0xffffffffU, 2}) == InsertResult::invalid_range);
  assert(layout.add({0x00000000U, 0}) == InsertResult::invalid_range);
  assert(layout.ranges().size() == 3);
  assert(layout.add({0x70100000U, 0x1000U}) == InsertResult::ok);
  const Guest32Range executable{0x400000U, 0x800000U};
  assert(!executable.contains(0x3fffffU));
  assert(executable.contains(0x400100U, 0x100U));
  assert(!executable.contains(0x400100U, kGuest32Limit));
  std::cout << "guest32_ranges: PASS\n";
}
