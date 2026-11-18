#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile a Win64 static-recompiler output directory into PS5 ELF objects.
# Works for public synthetic fixtures and for private user-owned game lifts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${PS5_PAYLOAD_SDK:-}"
FW="${NIGHTSIGHT_FW:-}"
GEN="${REFROZEN_GENERATED_DIR:-}"
OUT="${REFROZEN_GENERATED_OUT:-$ROOT/build/ps5-win64-generated-objects}"
JOBS="${BUILD_JOBS:-2}"

if [[ -z "$SDK" || ! -x "$SDK/bin/prospero-clang" ]]; then
  echo "PS5_PAYLOAD_SDK must point to the installed Payload SDK" >&2
  exit 2
fi
if [[ -z "$FW" || ! -f "$FW/runtime/cpu.h" || ! -f "$FW/runtime/tables.h" ]]; then
  echo "NIGHTSIGHT_FW must point to the pinned Recomp-Framework checkout" >&2
  exit 2
fi
if [[ -z "$GEN" || ! -d "$GEN" || ! -s "$GEN/tables.c" || ! -s "$GEN/funcs.h" ]]; then
  echo "REFROZEN_GENERATED_DIR must contain tables.c, funcs.h and code_*.c" >&2
  exit 2
fi
if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
  echo "BUILD_JOBS must be a positive integer" >&2
  exit 2
fi

shopt -s nullglob
CODE=("$GEN"/code_*.c)
if (( ${#CODE[@]} == 0 )); then
  echo "REFROZEN_GENERATED_DIR contains no code_*.c files" >&2
  exit 2
fi

mkdir -p "$OUT/obj"
rm -f "$OUT/objects.list" "$OUT/generated-files.list"

COMMON=(
  -std=gnu11 -O2 -g0
  "-ffile-prefix-map=$ROOT/=source/"
  "-fdebug-prefix-map=$ROOT/=source/"
  "-ffile-prefix-map=$SDK/=sdk/"
  "-fdebug-prefix-map=$SDK/=sdk/"
  -Wno-unused-variable
  -Wno-unused-but-set-variable
  -Wno-unused-label
  -Wno-unknown-pragmas
  -I"$FW/runtime"
  -I"$GEN"
)

compile_one() {
  local src=$1
  local base obj
  base=$(basename "$src" .c)
  obj="$OUT/obj/$base.o"
  "$SDK/bin/prospero-clang" "${COMMON[@]}" -c "$src" -o "$obj"
}

if (( JOBS == 1 )); then
  for src in "${CODE[@]}"; do compile_one "$src"; done
else
  export ROOT SDK FW GEN OUT
  printf '%s\0' "${CODE[@]}" | xargs -0 -n1 -P"$JOBS" bash -c '
    src=$1
    base=$(basename "$src" .c)
    obj="$OUT/obj/$base.o"
    "$SDK/bin/prospero-clang" \
      -std=gnu11 -O2 -g0 \
      "-ffile-prefix-map=$ROOT/=source/" \
      "-fdebug-prefix-map=$ROOT/=source/" \
      "-ffile-prefix-map=$SDK/=sdk/" \
      "-fdebug-prefix-map=$SDK/=sdk/" \
      -Wno-unused-variable -Wno-unused-but-set-variable \
      -Wno-unused-label -Wno-unknown-pragmas \
      -I"$FW/runtime" -I"$GEN" \
      -c "$src" -o "$obj"
  ' _
fi

"$SDK/bin/prospero-clang" "${COMMON[@]}" -c "$GEN/tables.c" -o "$OUT/obj/tables.o"

{
  for src in "${CODE[@]}"; do basename "$src"; done
  echo "tables.c"
} > "$OUT/generated-files.list"

{
  for src in "${CODE[@]}"; do
    printf '%s\n' "$OUT/obj/$(basename "$src" .c).o"
  done
  printf '%s\n' "$OUT/obj/tables.o"
} > "$OUT/objects.list"

while IFS= read -r obj; do
  test -s "$obj"
done < "$OUT/objects.list"

printf 'REFROZEN_PS5_GENERATED_OBJECTS pass=1 code_files=%d objects=%d\n' \
  "${#CODE[@]}" "$(( ${#CODE[@]} + 1 ))" | tee "$OUT/receipt.txt"
printf '%s\n' "$OUT/objects.list"
