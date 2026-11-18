#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile public patched x86recomp runtime sources only; no Warcraft assets.
set -euo pipefail
if (( $# != 4 )); then
  echo "usage: $0 PATCHED_RUNTIME_ROOT SDL_HEADERS_PATH CENSUS_TSV OUT_DIR" >&2
  exit 2
fi
RUNTIME=$1
SDL=$2
CENSUS=$3
OUT=$4
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SDK=${PS5_PAYLOAD_SDK:?PS5_PAYLOAD_SDK must be set}
CXX="$SDK/bin/prospero-clang++"
for path in "$RUNTIME" "$SDL" "$CENSUS" "$CXX"; do
  test -e "$path" || { echo "missing input: $path" >&2; exit 2; }
done
command -v ld.lld-18 >/dev/null
command -v llvm-nm-18 >/dev/null
command -v llvm-readobj-18 >/dev/null
mkdir -p "$OUT/objects" "$OUT/logs"
printf 'file\tstatus\n' > "$OUT/object-results.tsv"
objects=()
passed=0
failed=0
while IFS=$'\t' read -r relative state _; do
  if [[ "$relative" == "file" || "$state" != "PASS" ]]; then continue; fi
  if [[ "$relative" == /* || "$relative" == *..* || ! -f "$RUNTIME/$relative" ]]; then
    echo "unsafe or missing census path" >&2
    exit 2
  fi
  label="$(printf '%s' "$relative" | tr '/' '_')"
  object="$OUT/objects/$label.o"
  log="$OUT/logs/$label.log"
  if "$CXX" -std=c++20 -O0 -g0 -fPIC \
       -I"$ROOT/build/x86recomp/src" -I"$ROOT/ps5/runtime" -I"$SDL" \
       -c "$RUNTIME/$relative" -o "$object" >"$log" 2>&1 && [[ -s "$object" ]]; then
    printf '%s\tPASS\n' "$relative" >> "$OUT/object-results.tsv"
    objects+=("$object")
    ((passed+=1))
  else
    printf '%s\tFAIL\n' "$relative" >> "$OUT/object-results.tsv"
    echo "object failed: $relative" >&2
    grep -m1 -E 'fatal error:| error:' "$log" >&2 || true
    ((failed+=1))
  fi
done < "$CENSUS"
if (( failed > 0 || passed < 55 )); then
  echo "PS5 Win32 closure regression: pass=$passed fail=$failed" >&2
  exit 1
fi
ld.lld-18 -r "${objects[@]}" -o "$OUT/win32-runtime-closure.o"
llvm-readobj-18 --file-headers "$OUT/win32-runtime-closure.o" > "$OUT/elf-header.txt"
grep -Eq 'Machine: EM_X86_64|Arch: x86_64' "$OUT/elf-header.txt"
llvm-nm-18 --undefined-only "$OUT/win32-runtime-closure.o" | sort -u > "$OUT/unresolved-symbols.txt"
llvm-nm-18 --defined-only "$OUT/win32-runtime-closure.o" | sort -u > "$OUT/defined-symbols.txt"
unresolved="$(wc -l < "$OUT/unresolved-symbols.txt" | tr -d ' ')"
defined="$(wc -l < "$OUT/defined-symbols.txt" | tr -d ' ')"
echo "REFROZEN_PS5_WIN32_CLOSURE pass=1 objects=$passed aggregate=1 undefined_lines=$unresolved defined_lines=$defined" | tee "$OUT/receipt.txt"
