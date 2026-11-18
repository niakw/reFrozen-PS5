#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build a PS5 ELF that runs translated code from the public synthetic Win64 PE.
# No Warcraft binaries or generated Warcraft code are accepted by this script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${PS5_PAYLOAD_SDK:-}"
FW="${NIGHTSIGHT_FW:-}"
GEN="${REFROZEN_GENERATED_DIR:-}"
PE="${REFROZEN_SYNTHETIC_PE:-}"
if [[ -z "$SDK" || ! -x "$SDK/bin/prospero-clang" || ! -x "$SDK/bin/prospero-clang++" ]]; then
  echo "PS5_PAYLOAD_SDK must point to the installed Payload SDK" >&2
  exit 2
fi
if [[ -z "$FW" || ! -f "$FW/runtime/cpu.h" ]]; then
  echo "NIGHTSIGHT_FW must point to the pinned Recomp-Framework checkout" >&2
  exit 2
fi
if [[ -z "$GEN" || ! -s "$GEN/code_0000.c" || ! -s "$GEN/funcs.h" ]]; then
  echo "REFROZEN_GENERATED_DIR must contain synthetic Win64 translated C" >&2
  exit 2
fi
if [[ -z "$PE" || ! -s "$PE" ]]; then
  echo "REFROZEN_SYNTHETIC_PE must point to the public synthetic Win64 PE" >&2
  exit 2
fi

OUTDIR="$ROOT/build/ps5-win64-chain"
OUT="$OUTDIR/refrozen-synthetic-win64-chain.elf"
mkdir -p "$OUTDIR"
python3 "$ROOT/scripts/ps5/bin2cpp.py" "$PE" "$OUTDIR/synthetic_pe_blob.cpp" \
  --symbol g_refrozen_synthetic_pe

COMMON_MAP=( 
  "-ffile-prefix-map=$ROOT/=source/"
  "-fdebug-prefix-map=$ROOT/=source/"
  "-ffile-prefix-map=$SDK/=sdk/"
  "-fdebug-prefix-map=$SDK/=sdk/"
)

"$SDK/bin/prospero-clang" \
  -std=gnu11 -O2 -g0 \
  "${COMMON_MAP[@]}" \
  -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unused-label \
  -Wno-unknown-pragmas \
  -I"$FW/runtime" -I"$GEN" \
  -c "$GEN/code_0000.c" -o "$OUTDIR/synthetic-win64-lift.o"

"$SDK/bin/prospero-clang++" \
  -std=c++20 -O1 -g \
  "${COMMON_MAP[@]}" \
  -Wall -Wextra -Werror -Wpedantic -Wconversion \
  -I"$ROOT/ps5/host" -I"$ROOT/ps5/runtime" -I"$FW/runtime" -I"$GEN" \
  "$ROOT/tests/ps5/ps5_win64_chain_main.cpp" \
  "$OUTDIR/synthetic_pe_blob.cpp" \
  "$ROOT/ps5/runtime/exact_reservation_ps5.cpp" \
  "$ROOT/ps5/runtime/direct_guest_backing_ps5.cpp" \
  "$ROOT/ps5/runtime/guest_image_mapping_ps5.cpp" \
  "$OUTDIR/synthetic-win64-lift.o" \
  -o "$OUT"

test -s "$OUT"
printf '%s\n' "$OUT"
