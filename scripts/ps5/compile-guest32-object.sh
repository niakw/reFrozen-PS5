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
  -DCMAKE_BUILD_TYPE=Debug -DREFROZEN_PS5_COMPILE_ONLY=ON
cmake --build "$BUILD" --target guest32_ranges_compile guest64_ranges_compile --parallel 2
for name in guest32_ranges guest64_ranges; do
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
echo "PS5-target guest32 and guest64 objects compiled; NOT a linked PS5 executable."
