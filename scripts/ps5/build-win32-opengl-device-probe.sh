#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile/link the public PS5 OpenGL gfx::Device replacement. No game files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
X86=${1:?usage: build-win32-opengl-device-probe.sh X86RECOMP_ROOT OUT_DIR}
OUT=${2:?usage: build-win32-opengl-device-probe.sh X86RECOMP_ROOT OUT_DIR}
SDK=${PS5_PAYLOAD_SDK:?PS5_PAYLOAD_SDK is required}
GLSDK=${PS5_OPENGL_PREFIX:?PS5_OPENGL_PREFIX is required}
[[ -d "$X86/src/runtime/gfx" ]] || { echo "patched x86recomp runtime missing" >&2; exit 2; }
[[ -x "$SDK/bin/prospero-clang++" ]] || { echo "prospero-clang++ missing" >&2; exit 2; }
[[ -f "$GLSDK/share/ps5-opengl/ps5-opengl.mk" ]] || { echo "PS5 OpenGL SDK missing" >&2; exit 2; }
[[ -f "$GLSDK/manifest.sha256" ]] || { echo "PS5 OpenGL manifest missing" >&2; exit 2; }
(cd "$GLSDK" && sha256sum --check --strict manifest.sha256 >/dev/null)

rm -rf "$OUT"
mkdir -p "$OUT"
cat > "$OUT/Makefile" <<'MAKE'
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk
include $(PS5_OPENGL_PREFIX)/share/ps5-opengl/ps5-opengl.mk

ROOT := $(REFROZEN_ROOT)
X86 := $(X86RECOMP_ROOT)
BUILD := $(OUT_DIR)

CPPFLAGS += $(PS5_OPENGL_PUBLIC_CFLAGS) -I$(ROOT) -I$(X86)/src -I$(ROOT)/ps5/graphics
CXXFLAGS += -std=c++20 -O0 -g0 -Wall -Wextra -Werror -Wpedantic
OBJECTS := \
  $(BUILD)/probe.o \
  $(BUILD)/ps5_gl_device.o \
  $(BUILD)/wgl_platform_contract.o \
  $(BUILD)/wgl_egl_backend_ps5.o \
  $(BUILD)/device.o \
  $(BUILD)/format.o

$(BUILD)/probe.o: $(ROOT)/tests/ps5/ps5_win32_opengl_device_link_probe.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/ps5_gl_device.o: $(ROOT)/ps5/runtime/x86recomp_ps5_gl_device.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/wgl_platform_contract.o: $(ROOT)/ps5/graphics/wgl_platform_contract.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/wgl_egl_backend_ps5.o: $(ROOT)/ps5/graphics/wgl_egl_backend_ps5.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/device.o: $(X86)/src/runtime/gfx/device.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/format.o: $(X86)/src/runtime/gfx/format.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BUILD)/refrozen-win32-opengl-device.elf: $(OBJECTS)
	$(CXX) -o $@ $^ $(PS5_OPENGL_LDLIBS) $(PS5_OPENGL_LDFLAGS)

all: $(BUILD)/refrozen-win32-opengl-device.elf
.PHONY: all
MAKE

make -f "$OUT/Makefile" -j2 \
  PS5_PAYLOAD_SDK="$SDK" PS5_OPENGL_PREFIX="$GLSDK" \
  REFROZEN_ROOT="$ROOT" X86RECOMP_ROOT="$X86" OUT_DIR="$OUT" all

ELF="$OUT/refrozen-win32-opengl-device.elf"
test -s "$ELF"
llvm-readelf-18 -h -d "$ELF" > "$OUT/elf-metadata.txt"
llvm-nm-18 "$ELF" > "$OUT/symbols.txt"
llvm-nm-18 -u "$ELF" > "$OUT/undefined-symbols.txt" || true
sha256sum "$ELF" > "$OUT/SHA256SUMS"
grep -Eq 'Machine:.*X86-64|Machine:.*x86-64' "$OUT/elf-metadata.txt"
grep -q 'CreateGpuDevice' "$OUT/symbols.txt"
grep -q 'Ps5GlDevice' "$OUT/symbols.txt"
printf 'REFROZEN_PS5_WIN32_OPENGL_DEVICE_LINK pass=1 elf=%s undefined_lines=%s\n' \
  "$(basename "$ELF")" "$(wc -l < "$OUT/undefined-symbols.txt" | tr -d ' ')" | tee "$OUT/receipt.txt"
printf '%s\n' "$ELF"
