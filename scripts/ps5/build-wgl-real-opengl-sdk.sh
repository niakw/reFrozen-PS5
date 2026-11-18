#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build/link reFrozen WGL->EGL backend against an installed PS5 OpenGL SDK.
# This produces an ELF link probe only. Registered-title packaging/execution is separate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${PS5_PAYLOAD_SDK:-}"
GLSDK="${PS5_OPENGL_PREFIX:-}"
if [[ -z "$SDK" || ! -f "$SDK/toolchain/prospero.mk" ]]; then
  echo "PS5_PAYLOAD_SDK must point to Payload SDK v0.42-compatible tree" >&2
  exit 2
fi
if [[ -z "$GLSDK" || ! -f "$GLSDK/share/ps5-opengl/ps5-opengl.mk" ]]; then
  echo "PS5_OPENGL_PREFIX must point to installed PS5 OpenGL 4.6 SDK" >&2
  exit 2
fi
if [[ ! -f "$GLSDK/manifest.sha256" ]]; then
  echo "PS5 OpenGL manifest.sha256 is required" >&2
  exit 2
fi
(cd "$GLSDK" && sha256sum --check --strict manifest.sha256 >/dev/null)

OUT="$ROOT/build/ps5-real-opengl-sdk"
rm -rf "$OUT"
mkdir -p "$OUT"
cat > "$OUT/Makefile" <<'MAKE'
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk
include $(PS5_OPENGL_PREFIX)/share/ps5-opengl/ps5-opengl.mk
ROOT := $(REFROZEN_ROOT)
BUILD := $(ROOT)/build/ps5-real-opengl-sdk
CPPFLAGS += $(PS5_OPENGL_PUBLIC_CFLAGS) -I$(ROOT)/ps5/graphics
CXXFLAGS += -std=c++20 -O1 -g0 -Wall -Wextra -Werror -Wpedantic -Wconversion
OBJECTS := $(BUILD)/probe.o $(BUILD)/wgl_platform_contract.o $(BUILD)/wgl_egl_backend_ps5.o

$(BUILD)/probe.o: $(ROOT)/tests/ps5/ps5_wgl_egl_real_sdk_probe.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/wgl_platform_contract.o: $(ROOT)/ps5/graphics/wgl_platform_contract.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@
$(BUILD)/wgl_egl_backend_ps5.o: $(ROOT)/ps5/graphics/wgl_egl_backend_ps5.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BUILD)/refrozen-wgl-real-opengl.elf: $(OBJECTS)
	$(CXX) -o $@ $^ $(PS5_OPENGL_LDLIBS) $(PS5_OPENGL_LDFLAGS)

all: $(BUILD)/refrozen-wgl-real-opengl.elf
.PHONY: all
MAKE

make -f "$OUT/Makefile" -j2 \
  PS5_PAYLOAD_SDK="$SDK" PS5_OPENGL_PREFIX="$GLSDK" REFROZEN_ROOT="$ROOT" all
ELF="$OUT/refrozen-wgl-real-opengl.elf"
test -s "$ELF"
printf "%s\n" "$ELF"
