#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Link a tiny PS5 ELF that exercises only the synthetic guest-memory probe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${PS5_PAYLOAD_SDK:-}"
if [[ -z "$SDK" || ! -x "$SDK/bin/prospero-clang++" ]]; then
  echo "PS5_PAYLOAD_SDK must point to the installed Payload SDK" >&2
  exit 2
fi

OUTDIR="$ROOT/build/ps5-probe"
OUT="$OUTDIR/refrozen-guest-memory-probe.elf"
mkdir -p "$OUTDIR"

"$SDK/bin/prospero-clang++" \
  -std=c++20 -O1 -g \
  -ffile-prefix-map="$ROOT/=source/" \
  -fdebug-prefix-map="$ROOT/=source/" \
  -ffile-prefix-map="$SDK/=sdk/" \
  -fdebug-prefix-map="$SDK/=sdk/" \
  -Wall -Wextra -Werror -Wpedantic -Wconversion \
  -I"$ROOT/ps5/host" -I"$ROOT/ps5/runtime" \
  "$ROOT/tests/ps5/ps5_guest_memory_probe_main.cpp" \
  "$ROOT/ps5/runtime/exact_reservation_ps5.cpp" \
  "$ROOT/ps5/runtime/direct_guest_backing_ps5.cpp" \
  "$ROOT/ps5/runtime/guest_image_mapping_ps5.cpp" \
  "$ROOT/ps5/runtime/guest_memory_probe_ps5.cpp" \
  -o "$OUT"

test -s "$OUT"
printf '%s\n' "$OUT"
