// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest64_ranges.hpp"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>

using refrozen::ps5::Guest64InsertResult;
using refrozen::ps5::Guest64Layout;
using refrozen::ps5::Guest64Range;
using refrozen::ps5::overlaps;

constexpr std::uint64_t kMax = std::numeric_limits<std::uint64_t>::max();
static_assert(sizeof(std::uint64_t) == 8);
static_assert(Guest64Range{0x140000000ULL, 0x200000ULL}.valid());
static_assert(Guest64Range{0x140000000ULL, 0x200000ULL}.end() == 0x140200000ULL);
static_assert(Guest64Range{0x140000000ULL, 0x200000ULL}.contains(0x1401fffffULL));
static_assert(!Guest64Range{0x140000000ULL, 0x200000ULL}.contains(0x140200000ULL));
static_assert(!Guest64Range{kMax, 1}.valid());  // would need end == 2^64
static_assert(!Guest64Range{kMax - 1, 2}.valid());
static_assert(Guest64Range{kMax - 1, 1}.valid());
static_assert(!Guest64Range{0, 0}.valid());
static_assert(Guest64Range{0, 1}.valid());
static_assert(!overlaps({0x140000000ULL, 0x10000}, {0x140010000ULL, 0x10000}));
static_assert(overlaps({0x140000000ULL, 0x10000}, {0x14000ffffULL, 0x10000}));
static_assert(!overlaps({kMax, 1}, {kMax - 1, 1}));

int main() {
  Guest64Layout layout;
  // Synthetic image bases model normal Win64 process layouts.
  assert(layout.add({0x140000000ULL, 0x900000ULL}) == Guest64InsertResult::ok);
  assert(layout.add({0x180000000ULL, 0x400000ULL}) == Guest64InsertResult::ok);
  assert(layout.images().size() == 2);
  assert(layout.add({0x1408ffffULL, 2}) == Guest64InsertResult::overlap);
  assert(layout.add({0x180000000ULL, 0x10000ULL}) == Guest64InsertResult::overlap);
  assert(layout.add({0x140900000ULL, 0x1000ULL}) == Guest64InsertResult::ok);
  assert(layout.add({0x180000000ULL, 0}) == Guest64InsertResult::invalid_range);
  assert(layout.add({kMax - 31, 33}) == Guest64InsertResult::invalid_range);
  assert(layout.add({kMax - 32, 32}) == Guest64InsertResult::ok);
  assert(layout.images().size() == 4);
  const Guest64Range high{kMax - 32, 32};
  assert(high.contains(kMax - 1));
  assert(!high.contains(kMax));
  assert(!high.contains(kMax - 2, 3));
  assert(!high.contains(kMax - 2, kMax));
  std::cout << "guest64_ranges: PASS\n";
}
