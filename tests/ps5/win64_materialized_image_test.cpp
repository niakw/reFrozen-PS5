// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include "pe_image_materializer.hpp"
extern "C" {
#include "cpu.h"
void F_140001000(CPU *c);
}

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <span>
#include <sys/mman.h>
#include <vector>

using namespace refrozen::ps5;

int main(int argc, char** argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: %s synthetic.exe\n", argv[0]);
    return 2;
  }
  std::ifstream input(argv[1], std::ios::binary);
  std::vector<std::uint8_t> file((std::istreambuf_iterator<char>(input)),
                                 std::istreambuf_iterator<char>());
  if (file.empty()) {
    std::fprintf(stderr, "cannot read synthetic PE\n");
    return 2;
  }

  constexpr std::uint64_t base = 0x140000000ULL;
  constexpr std::size_t image_size = 0x5000;
#ifdef MAP_FIXED_NOREPLACE
  void* mapping = mmap(reinterpret_cast<void*>(base), image_size,
                       PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
                       -1, 0);
#else
#error "MAP_FIXED_NOREPLACE is required for safe host identity-map testing"
#endif
  if (mapping != reinterpret_cast<void*>(base)) {
    std::fprintf(stderr, "image reserve/map failed got=%p errno=%d (%s)\n",
                 mapping, errno, std::strerror(errno));
    if (mapping != MAP_FAILED) munmap(mapping, image_size);
    return 1;
  }

  const std::array sections{
      PeSectionCopy{".text", base + 0x1000, 0x10, 0x400, 0x200, 0x60000020},
      PeSectionCopy{".data", base + 0x2000, 0x04, 0x600, 0x200, 0xC0000040},
      PeSectionCopy{".pdata", base + 0x3000, 0x0C, 0x800, 0x200, 0x40000040},
      PeSectionCopy{".xdata", base + 0x4000, 0x04, 0xA00, 0x200, 0x40000040},
  };
  auto destination = std::span<std::uint8_t>(
      reinterpret_cast<std::uint8_t*>(mapping), image_size);
  const PeImageCopyLayout layout{base, image_size, 0x400, sections};
  const auto loaded = MaterializePeImage(file, destination, layout);
  if (!loaded.ok()) {
    std::fprintf(stderr, "materialize failed status=%d section=%.*s\n",
                 static_cast<int>(loaded.status),
                 static_cast<int>(loaded.section.size()), loaded.section.data());
    munmap(mapping, image_size);
    return 1;
  }

  auto* global = reinterpret_cast<volatile std::uint32_t*>(base + 0x2000);
  if (*global != 41) {
    std::fprintf(stderr, "PE data was not copied: value=%u\n",
                 static_cast<unsigned>(*global));
    munmap(mapping, image_size);
    return 1;
  }

  // The guest .xdata granule is data-only. The guest PE image never needs
  // PROT_EXEC because translated C/C++ is the code the host executes.
  if (mprotect(reinterpret_cast<void*>(base + 0x4000), 0x1000, PROT_READ) != 0) {
    std::perror("mprotect");
    munmap(mapping, image_size);
    return 1;
  }

  CPU state{};
  const std::uint64_t initial_rsp = 0x1000800ULL;
  state.rax = UINT64_MAX;
  state.rsp = initial_rsp;
  F_140001000(&state);

  const auto value = *global;
  const bool pass = value == 42 && state.rax == 42 &&
                    state.rsp == initial_rsp + 8 &&
                    state.fn == 0x140001000ULL;
  if (munmap(mapping, image_size) != 0) {
    std::perror("munmap");
    return 1;
  }
  if (!pass) {
    std::fprintf(stderr,
                 "materialized image semantics failed value=%u rax=%llu rsp=%llx fn=%llx\n",
                 static_cast<unsigned>(value),
                 static_cast<unsigned long long>(state.rax),
                 static_cast<unsigned long long>(state.rsp),
                 static_cast<unsigned long long>(state.fn));
    return 1;
  }
  std::puts("synthetic Win64 materialized PE -> translated function: PASS");
  return 0;
}
