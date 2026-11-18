#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile the PS5 first-launch subset of the pinned, already-patched Win64 runtime.
# steam.c and the original macOS vulkan.c are deliberately excluded.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME=${1:?usage: compile-win64-first-launch-runtime.sh RUNTIME_ROOT OUT_DIR}
OUT=${2:?usage: compile-win64-first-launch-runtime.sh RUNTIME_ROOT OUT_DIR}
SDK=${PS5_PAYLOAD_SDK:?PS5_PAYLOAD_SDK is required}
CC="$SDK/bin/prospero-clang"
JOBS="${BUILD_JOBS:-2}"
[[ -x "$CC" && -d "$RUNTIME" ]]
if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
  echo "BUILD_JOBS must be a positive integer" >&2
  exit 2
fi
if [[ -z "${REFROZEN_PS5_CDEPS:-}" || ! -d "$REFROZEN_PS5_CDEPS/include/openssl" || ! -s "$REFROZEN_PS5_CDEPS/lib/libcrypto.a" ]]; then
  echo "REFROZEN_PS5_CDEPS must contain pinned OpenSSL headers and lib/libcrypto.a" >&2
  exit 2
fi

UNITS=(
  bcrypt.c boot.c dinput.c display.c fiber.c files.c handles.c input.c
  kernel32.c native.c pdh.c rt.c sockets.c spvfix.c system.c teb.c
  user32.c wasapi.c window.c xaudio2.c xreverb.c
)

mkdir -p "$OUT/objects" "$OUT/logs"
rm -f "$OUT/objects.list" "$OUT/results.tsv"
printf 'file\tstatus\n' > "$OUT/results.tsv"

compile_unit() {
  local unit=$1
  local src="$RUNTIME/$unit"
  local obj="$OUT/objects/${unit%.c}.o"
  local log="$OUT/logs/$unit.log"
  if [[ ! -s "$src" ]]; then
    echo "$unit: source missing" > "$log"
    return 2
  fi
  "$CC" -std=gnu11 -O2 -g0 \
    -Wno-unknown-pragmas -Wno-deprecated-declarations \
    "-ffile-prefix-map=$ROOT/=source/" "-fdebug-prefix-map=$ROOT/=source/" \
    "-ffile-prefix-map=$SDK/=sdk/" "-fdebug-prefix-map=$SDK/=sdk/" \
    -I"$RUNTIME" -I"$ROOT/ps5/runtime" \
    -I"$(dirname "$RUNTIME")/third_party/vulkan/include" \
    -I"$REFROZEN_PS5_CDEPS/include" \
    -c "$src" -o "$obj" >"$log" 2>&1
}

# Keep deterministic result ordering; parallelize only compilation.
export ROOT RUNTIME OUT SDK CC REFROZEN_PS5_CDEPS
export -f compile_unit
if (( JOBS == 1 )); then
  for unit in "${UNITS[@]}"; do compile_unit "$unit"; done
else
  printf '%s\0' "${UNITS[@]}" | xargs -0 -n1 -P"$JOBS" bash -c '
    unit=$1
    src="$RUNTIME/$unit"
    obj="$OUT/objects/${unit%.c}.o"
    log="$OUT/logs/$unit.log"
    test -s "$src" || { echo "$unit: source missing" >"$log"; exit 2; }
    "$CC" -std=gnu11 -O2 -g0 \
      -Wno-unknown-pragmas -Wno-deprecated-declarations \
      "-ffile-prefix-map=$ROOT/=source/" "-fdebug-prefix-map=$ROOT/=source/" \
      "-ffile-prefix-map=$SDK/=sdk/" "-fdebug-prefix-map=$SDK/=sdk/" \
      -I"$RUNTIME" -I"$ROOT/ps5/runtime" \
      -I"$(dirname "$RUNTIME")/third_party/vulkan/include" \
      -I"$REFROZEN_PS5_CDEPS/include" \
      -c "$src" -o "$obj" >"$log" 2>&1
  ' _
fi

for unit in "${UNITS[@]}"; do
  obj="$OUT/objects/${unit%.c}.o"
  if [[ ! -s "$obj" ]]; then
    printf '%s\tFAIL\n' "$unit" >> "$OUT/results.tsv"
    cat "$OUT/logs/$unit.log" >&2 || true
    exit 1
  fi
  printf '%s\tPASS\n' "$unit" >> "$OUT/results.tsv"
  printf '%s\n' "$obj" >> "$OUT/objects.list"
done

# Native PS5 audio output used by both patched XAudio2 and WASAPI.
"$CC" -std=gnu11 -O2 -g0 -Wall -Wextra -Werror \
  -I"$ROOT/ps5/runtime" \
  -c "$ROOT/ps5/runtime/ps5_audio_out_bridge.c" \
  -o "$OUT/objects/ps5_audio_out_bridge.o"
printf '%s\n' "$OUT/objects/ps5_audio_out_bridge.o" >> "$OUT/objects.list"

count=$(wc -l < "$OUT/objects.list" | tr -d ' ')
if [[ "$count" -ne 22 ]]; then
  echo "unexpected first-launch object count: $count (expected 22)" >&2
  exit 1
fi

# Relocatable aggregation catches duplicate definitions and incompatible PS5
# object formats while intentionally leaving libc/platform/game imports unresolved.
mapfile -t OBJECTS < "$OUT/objects.list"
LLD="${REFROZEN_HOST_LLD:-ld.lld-18}"
if ! command -v "$LLD" >/dev/null 2>&1; then
  echo "missing host relocatable linker: $LLD" >&2
  exit 2
fi
"$LLD" -r "${OBJECTS[@]}" -o "$OUT/first-launch-runtime.o"
test -s "$OUT/first-launch-runtime.o"

printf 'REFROZEN_PS5_WIN64_RUNTIME_OBJECTS pass=1 runtime_units=21 objects=%s aggregate=1 excluded=steam.c,vulkan.c\n' "$count" \
  | tee "$OUT/receipt.txt"
printf '%s\n' "$OUT/objects.list"
