#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile each C translation unit independently for the PS5 ABI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME=${1:?usage: compile-win64-runtime-census.sh RUNTIME_ROOT OUT_DIR}
OUT=${2:?usage: compile-win64-runtime-census.sh RUNTIME_ROOT OUT_DIR}
SDK=${PS5_PAYLOAD_SDK:?PS5_PAYLOAD_SDK is required}
CC="$SDK/bin/prospero-clang"
[[ -x "$CC" && -d "$RUNTIME" ]]
mkdir -p "$OUT/logs" "$OUT/objects"
printf 'file\tstatus\n' > "$OUT/results.tsv"
passed=0
failed=0
for src in "$RUNTIME"/*.c; do
  [[ -f "$src" ]] || continue
  name=${src##*/}
  obj="$OUT/objects/${name%.c}.o"
  log="$OUT/logs/$name.log"
  if "$CC" -std=gnu11 -O0 -g0 \
      -Wno-unknown-pragmas -Wno-deprecated-declarations \
      -I"$RUNTIME" -I"$ROOT/ps5/runtime" -I"$(dirname "$RUNTIME")/third_party/vulkan/include" \
      -c "$src" -o "$obj" >"$log" 2>&1; then
    printf '%s\tPASS\n' "$name" >> "$OUT/results.tsv"
    passed=$((passed + 1))
  else
    rm -f "$obj"
    printf '%s\tFAIL\n' "$name" >> "$OUT/results.tsv"
    failed=$((failed + 1))
  fi
done
printf 'passed=%d failed=%d\n' "$passed" "$failed" | tee "$OUT/summary.txt"
[[ $passed -gt 0 ]]
