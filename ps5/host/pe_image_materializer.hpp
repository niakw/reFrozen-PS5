// SPDX-License-Identifier: GPL-3.0-or-later
// Host-independent materialization of a validated PE image into an already
// reserved/mapped identity-address range. No OS mapping calls here.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <string_view>

namespace refrozen::ps5 {

struct PeSectionCopy {
  std::string_view name;
  std::uint64_t address{};
  std::uint64_t virtual_size{};
  std::size_t file_offset{};
  std::size_t file_size{};
  std::uint32_t characteristics{};
};

struct PeImageCopyLayout {
  std::uint64_t base{};
  std::uint64_t image_size{};
  std::size_t headers_size{};
  std::span<const PeSectionCopy> sections;
};

enum class PeMaterializeStatus {
  ok,
  invalid_layout,
  destination_size_mismatch,
  headers_truncated,
  section_outside_image,
  section_file_truncated,
  overlapping_sections,
};

struct PeMaterializeResult {
  PeMaterializeStatus status{PeMaterializeStatus::invalid_layout};
  std::size_t bytes_copied{};
  std::size_t bytes_zeroed{};
  std::string_view section;

  [[nodiscard]] constexpr bool ok() const noexcept {
    return status == PeMaterializeStatus::ok;
  }
};

[[nodiscard]] inline PeMaterializeResult MaterializePeImage(
    std::span<const std::uint8_t> file,
    std::span<std::uint8_t> destination,
    const PeImageCopyLayout& layout) {
  PeMaterializeResult result{};
  if (!layout.image_size || layout.image_size > destination.size() ||
      layout.image_size > static_cast<std::uint64_t>(SIZE_MAX) ||
      layout.base > UINT64_MAX - layout.image_size ||
      layout.headers_size > layout.image_size) {
    result.status = PeMaterializeStatus::invalid_layout;
    return result;
  }
  if (destination.size() != static_cast<std::size_t>(layout.image_size)) {
    result.status = PeMaterializeStatus::destination_size_mismatch;
    return result;
  }
  if (layout.headers_size > file.size()) {
    result.status = PeMaterializeStatus::headers_truncated;
    return result;
  }

  // Reject ambiguous section memory ranges before modifying the destination.
  for (std::size_t i = 0; i < layout.sections.size(); ++i) {
    const auto& a = layout.sections[i];
    const std::uint64_t a_size = a.virtual_size ? a.virtual_size : a.file_size;
    if (!a_size || a.address < layout.base ||
        a.address > layout.base + layout.image_size ||
        a_size > layout.base + layout.image_size - a.address) {
      result.status = PeMaterializeStatus::section_outside_image;
      result.section = a.name;
      return result;
    }
    const auto a_memory_size = static_cast<std::size_t>(a_size);
    const auto a_copy_size = std::min(a.file_size, a_memory_size);
    if (a.file_offset > file.size() ||
        a_copy_size > file.size() - a.file_offset) {
      result.status = PeMaterializeStatus::section_file_truncated;
      result.section = a.name;
      return result;
    }
    for (std::size_t j = i + 1; j < layout.sections.size(); ++j) {
      const auto& b = layout.sections[j];
      const std::uint64_t b_size = b.virtual_size ? b.virtual_size : b.file_size;
      if (!b_size || b.address < layout.base ||
          b.address > layout.base + layout.image_size ||
          b_size > layout.base + layout.image_size - b.address) {
        result.status = PeMaterializeStatus::section_outside_image;
        result.section = b.name;
        return result;
      }
      const auto a_end = a.address + a_size;
      const auto b_end = b.address + b_size;
      if (a.address < b_end && b.address < a_end) {
        result.status = PeMaterializeStatus::overlapping_sections;
        result.section = b.name;
        return result;
      }
    }
  }

  std::fill(destination.begin(), destination.end(), std::uint8_t{0});
  result.bytes_zeroed = destination.size();
  if (layout.headers_size) {
    std::memcpy(destination.data(), file.data(), layout.headers_size);
    result.bytes_copied += layout.headers_size;
  }

  for (const auto& section : layout.sections) {
    const auto memory_size = static_cast<std::size_t>(
        section.virtual_size ? section.virtual_size : section.file_size);
    const auto copy_size = std::min(section.file_size, memory_size);
    const auto destination_offset =
        static_cast<std::size_t>(section.address - layout.base);
    if (copy_size) {
      std::memcpy(destination.data() + destination_offset,
                  file.data() + section.file_offset, copy_size);
      result.bytes_copied += copy_size;
    }
  }

  result.status = PeMaterializeStatus::ok;
  return result;
}

}  // namespace refrozen::ps5
