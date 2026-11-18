#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile synthetic guest-layout checks for the PS5 ABI: object only.
# Does not link a PS5 executable, package a PKG, or use game data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -z "${PS5_PAYLOAD_SDK:-}" || ! -d "${PS5_PAYLOAD_SDK:-}/target/include" ]]; then
  echo "PS5_PAYLOAD_SDK must point to a payload SDK with target/include" >&2
  exit 2
fi
for cmd in clang++-18 llvm-ar-18 llvm-ranlib-18 llvm-readobj-18 cmake; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing PS5 cross compilation dependency: $cmd" >&2
    exit 2
  fi
done

BUILD="$ROOT/build/ps5-sdk-smoke"
cmake -S "$ROOT/tests/ps5" -B "$BUILD" \
  -DCMAKE_TOOLCHAIN_FILE="$ROOT/ps5/toolchain/ps5-payload.cmake" \
  -DCMAKE_BUILD_TYPE=Debug -DREFROZEN_PS5_COMPILE_ONLY=ON \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$BUILD" --target \
  guest32_ranges_compile guest64_ranges_compile exact_guest_reservation_compile \
  pe_image_materializer_compile direct_guest_backing_compile guest_image_mapping_compile \
  ps5_exact_reservation_adapter_compile ps5_direct_guest_backing_adapter_compile \
  ps5_guest_image_mapping_adapter_compile ps5_guest_memory_probe_compile --parallel 2
for name in guest32_ranges guest64_ranges exact_guest_reservation pe_image_materializer direct_guest_backing guest_image_mapping; do
  object="$BUILD/CMakeFiles/${name}_compile.dir/${name}_test.cpp.o"
  if [[ ! -s "$object" ]]; then
    echo "Missing PS5 compile-only object: $object" >&2
    exit 1
  fi
  llvm-readobj-18 --file-headers "$object" > "$BUILD/${name}-object-header.txt"
  if ! grep -Eq 'Arch: x86_64|Machine: EM_X86_64' "$BUILD/${name}-object-header.txt"; then
    cat "$BUILD/${name}-object-header.txt" >&2
    echo "Object is not x86-64; inspect target triple and SDK" >&2
    exit 1
  fi
done
for target in ps5_exact_reservation_adapter ps5_direct_guest_backing_adapter ps5_guest_image_mapping_adapter ps5_guest_memory_probe; do
  adapter_object="$(find "$BUILD/CMakeFiles/${target}_compile.dir" -type f -name '*.o' -print -quit)"
  if [[ -z "$adapter_object" || ! -s "$adapter_object" ]]; then
    echo "Missing PS5 adapter object: $target" >&2
    exit 1
  fi
  llvm-readobj-18 --file-headers "$adapter_object" > "$BUILD/${target}-object-header.txt"
  if ! grep -Eq 'Arch: x86_64|Machine: EM_X86_64' "$BUILD/${target}-object-header.txt"; then
    cat "$BUILD/${target}-object-header.txt" >&2
    echo "PS5 adapter object is not x86-64: $target" >&2
    exit 1
  fi
done
echo "PS5-target guest layout/reservation/backing/mapping/probe objects compiled; NOT a linked PS5 executable."
