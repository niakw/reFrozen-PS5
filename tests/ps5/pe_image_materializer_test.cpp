// SPDX-License-Identifier: GPL-3.0-or-later
#include "pe_image_materializer.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

using namespace refrozen::ps5;

int main() {
  constexpr std::uint64_t base = 0x140000000ULL;
  std::vector<std::uint8_t> file(0x600, 0);
  for (std::size_t i = 0; i < 0x100; ++i) file[i] = static_cast<std::uint8_t>(i);
  for (std::size_t i = 0; i < 0x10; ++i) file[0x200 + i] = static_cast<std::uint8_t>(0x80 + i);
  for (std::size_t i = 0; i < 0x20; ++i) file[0x300 + i] = static_cast<std::uint8_t>(0x40 + i);

  const std::array sections{
      PeSectionCopy{".text", base + 0x1000, 0x20, 0x200, 0x10, 0x60000020},
      PeSectionCopy{".data", base + 0x2000, 0x20, 0x300, 0x20, 0xC0000040},
  };
  const PeImageCopyLayout layout{base, 0x4000, 0x100, sections};
  std::vector<std::uint8_t> image(0x4000, 0xCD);

  const auto result = MaterializePeImage(file, image, layout);
  assert(result.ok());
  assert(result.bytes_copied == 0x100 + 0x10 + 0x20);
  assert(result.bytes_zeroed == image.size());
  assert(std::equal(file.begin(), file.begin() + 0x100, image.begin()));
  assert(std::equal(file.begin() + 0x200, file.begin() + 0x210,
                    image.begin() + 0x1000));
  assert(std::all_of(image.begin() + 0x1010, image.begin() + 0x1020,
                     [](std::uint8_t v) { return v == 0; }));
  assert(std::equal(file.begin() + 0x300, file.begin() + 0x320,
                    image.begin() + 0x2000));
  assert(image[0x3000] == 0);

  {
    auto bad_sections = sections;
    bad_sections[1].file_offset = file.size() - 4;
    bad_sections[1].file_size = 0x20;
    std::vector<std::uint8_t> untouched(0x4000, 0xA5);
    const auto bad = MaterializePeImage(
        file, untouched, PeImageCopyLayout{base, 0x4000, 0x100, bad_sections});
    assert(bad.status == PeMaterializeStatus::section_file_truncated);
    assert(bad.section == ".data");
    assert(std::all_of(untouched.begin(), untouched.end(),
                       [](std::uint8_t v) { return v == 0xA5; }));
  }
  {
    const std::array overlapping{
        PeSectionCopy{".one", base + 0x1000, 0x1000, 0x200, 0x10, 0},
        PeSectionCopy{".two", base + 0x1800, 0x1000, 0x300, 0x10, 0},
    };
    std::vector<std::uint8_t> untouched(0x4000, 0xA5);
    const auto bad = MaterializePeImage(
        file, untouched, PeImageCopyLayout{base, 0x4000, 0x100, overlapping});
    assert(bad.status == PeMaterializeStatus::overlapping_sections);
    assert(std::all_of(untouched.begin(), untouched.end(),
                       [](std::uint8_t v) { return v == 0xA5; }));
  }
  {
    const std::array outside{
        PeSectionCopy{".bad", base + 0x3800, 0x1000, 0x200, 0x10, 0},
    };
    std::vector<std::uint8_t> untouched(0x4000, 0xA5);
    const auto bad = MaterializePeImage(
        file, untouched, PeImageCopyLayout{base, 0x4000, 0x100, outside});
    assert(bad.status == PeMaterializeStatus::section_outside_image);
  }

  std::cout << "pe_image_materializer: PASS\n";
}
