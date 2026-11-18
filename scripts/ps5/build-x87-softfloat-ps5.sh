#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build x87.cpp + sse.cpp and pinned Berkeley SoftFloat for the PS5 ABI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
X86=${1:?usage: build-x87-softfloat-ps5.sh X86RECOMP_ROOT SOFTFLOAT_ROOT OUT_DIR}
SOFTFLOAT=${2:?usage: build-x87-softfloat-ps5.sh X86RECOMP_ROOT SOFTFLOAT_ROOT OUT_DIR}
OUT=${3:?usage: build-x87-softfloat-ps5.sh X86RECOMP_ROOT SOFTFLOAT_ROOT OUT_DIR}
SDK=${PS5_PAYLOAD_SDK:?PS5_PAYLOAD_SDK is required}
[[ -f "$X86/cmake/softfloat.cmake" ]] || { echo "x86recomp SoftFloat recipe missing" >&2; exit 2; }
[[ -f "$SOFTFLOAT/source/include/softfloat.h" ]] || { echo "pinned SoftFloat source missing" >&2; exit 2; }
[[ -x "$SDK/bin/prospero-clang++" ]] || { echo "prospero compiler missing" >&2; exit 2; }
command -v cmake >/dev/null
command -v llvm-nm-18 >/dev/null
command -v llvm-readobj-18 >/dev/null
command -v ld.lld-18 >/dev/null

rm -rf "$OUT"
cmake -S "$ROOT/tests/ps5/x87" -B "$OUT" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ROOT/ps5/toolchain/payload-sdk-prospero.cmake" \
  -DX86RECOMP_ROOT="$X86" \
  -DFETCHCONTENT_SOURCE_DIR_SOFTFLOAT="$SOFTFLOAT" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$OUT" --target refrozen_x87_ps5 softfloat --parallel 2

mapfile -t x87libs < <(find "$OUT" -type f -name "librefrozen_x87_ps5.a" -print)
mapfile -t softlibs < <(find "$OUT" -type f -name "libsoftfloat.a" -print)
[[ ${#x87libs[@]} -eq 1 ]] || { echo "expected one x87 archive, found ${#x87libs[@]}" >&2; exit 1; }
[[ ${#softlibs[@]} -eq 1 ]] || { echo "expected one SoftFloat archive, found ${#softlibs[@]}" >&2; exit 1; }
x87lib=${x87libs[0]}
softlib=${softlibs[0]}

ld.lld-18 -r --whole-archive "$x87lib" "$softlib" --no-whole-archive -o "$OUT/x87-softfloat-ps5.o"
test -s "$OUT/x87-softfloat-ps5.o"
llvm-readobj-18 --file-headers "$OUT/x87-softfloat-ps5.o" > "$OUT/elf-header.txt"
grep -Eq 'Machine: EM_X86_64|Arch: x86_64' "$OUT/elf-header.txt"
llvm-nm-18 --undefined-only "$OUT/x87-softfloat-ps5.o" | sort -u > "$OUT/unresolved-symbols.txt"
llvm-nm-18 --defined-only "$OUT/x87-softfloat-ps5.o" | sort -u > "$OUT/defined-symbols.txt"
if grep -E '(^| )(_?softfloat_|_?(extF80|f16|f32|f64|f128|ui32|ui64|i32|i64)_)' "$OUT/unresolved-symbols.txt" > "$OUT/unresolved-softfloat.txt"; then
  cat "$OUT/unresolved-softfloat.txt" >&2
  echo "SoftFloat API closure is incomplete" >&2
  exit 1
fi
printf 'REFROZEN_PS5_X87_SOFTFLOAT pass=1 undefined_lines=%s defined_lines=%s\n' \
  "$(wc -l < "$OUT/unresolved-symbols.txt" | tr -d ' ')" \
  "$(wc -l < "$OUT/defined-symbols.txt" | tr -d ' ')" | tee "$OUT/receipt.txt"
