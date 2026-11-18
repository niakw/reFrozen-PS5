#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build a registered native PS5 folder for the reFrozen WGL/EGL compatibility probe.
# Requires the already installed/verified PS5 OpenGL SDK. No Warcraft files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${PS5_PAYLOAD_SDK:-}"
GLSDK="${PS5_OPENGL_PREFIX:-}"
GLROOT="${REFROZEN_OPENGL_SOURCE_ROOT:-}"
TEMPLATE="${REFROZEN_NATIVE_TEMPLATE:-}"
for value in SDK GLSDK GLROOT TEMPLATE; do
  [[ -n "${!value}" ]] || { echo "$value is required" >&2; exit 2; }
done
[[ -x "$SDK/bin/prospero-lld" && -d "$SDK/target/include" ]] || { echo "invalid PS5_PAYLOAD_SDK" >&2; exit 2; }
[[ -f "$GLSDK/manifest.sha256" && -f "$GLSDK/lib/libPS5OpenGL.a" ]] || { echo "invalid PS5 OpenGL SDK" >&2; exit 2; }
[[ -f "$GLROOT/native-app/app_heap.c" && -f "$GLROOT/native-app/ps5-pie.ld" ]] || { echo "invalid OpenGL source root" >&2; exit 2; }
[[ -f "$TEMPLATE/Makefile" && -f "$TEMPLATE/tools/build.sh" ]] || { echo "invalid native boilerplate" >&2; exit 2; }
(cd "$GLSDK" && sha256sum --check --strict manifest.sha256 >/dev/null)

TITLE=PPSA99006
APP="$ROOT/build/native-wgl-title/$TITLE"
rm -rf "$APP"
mkdir -p "$(dirname "$APP")"
cp -a "$TEMPLATE" "$APP"
rm -rf "$APP/.git" "$APP/.github"

# Give the boilerplate the exact already-verified Payload SDK. Its dependency
# bootstrap will keep it and build only its pinned host/native helper deps.
mkdir -p "$APP/.deps/native"
cp -a "$SDK" "$APP/.deps/native/ps5-payload-sdk"
APP_SDK="$APP/.deps/native/ps5-payload-sdk"

# OpenGL title integration copied from the vendored hardware-gate recipe.
cp "$APP/tooling/native/ps5-pie.ld" "$APP/tooling/native/ps5-pie-base.ld"
cp "$GLROOT/native-app/ps5-pie.ld" "$APP/tooling/native/ps5-pie.ld"
cp "$GLROOT/native-app/app-symbols.map" "$APP/tooling/native/app-symbols.map"
heap_source="$APP/tooling/native/sce_module_writer.cpp"
heap_default='write_u64(result.data, result.heap_size, std::numeric_limits<std::uint64_t>::max());'
[[ "$(grep -Fc "$heap_default" "$heap_source")" == 1 ]] || { echo "module-writer heap marker changed" >&2; exit 2; }
sed -i "s/$heap_default/write_u64(result.data, result.heap_size, 0x10000000ULL);/" "$heap_source"
link_script="$APP/tools/build.sh"
link_marker='--eh-frame-hdr \\'
[[ "$(grep -Fc -- "$link_marker" "$link_script")" == 1 ]] || { echo "native link marker changed" >&2; exit 2; }
sed -i 's/--eh-frame-hdr \\/--eh-frame-hdr --wrap=malloc --wrap=calloc --wrap=realloc --wrap=free --wrap=posix_memalign --wrap=malloc_usable_size \\'/ "$link_script"

rm -rf "$APP/src" "$APP/include" "$APP/vendor"
mkdir -p "$APP/src" "$APP/include" "$APP/vendor"
cp "$GLROOT/native-app/runtime_shims.c" "$APP/src/runtime_shims.c"
cp "$GLROOT/native-app/app_heap.c" "$APP/src/app_heap.c"
cp "$ROOT/tests/ps5/ps5_wgl_egl_title_probe.cpp" "$APP/src/main.cpp"
cp "$ROOT/ps5/graphics/wgl_platform_contract.cpp" "$APP/src/wgl_platform_contract.cpp"
cp "$ROOT/ps5/graphics/wgl_egl_backend_ps5.cpp" "$APP/src/wgl_egl_backend_ps5.cpp"
cp "$ROOT/ps5/graphics/wgl_platform_contract.hpp" "$APP/include/"
cp "$ROOT/ps5/graphics/wgl_egl_backend_ps5.hpp" "$APP/include/"
for headers in EGL GL KHR; do cp -a "$GLSDK/include/$headers" "$APP/include/"; done

# Dedicated test identity: no collision with Encore PPSA99008 or OpenGL PPSA99005.
python3 - "$GLROOT/native-app/param.json" "$APP/sce_sys/param.json" <<'PY'
import json, sys
from pathlib import Path
src=Path(sys.argv[1]); dst=Path(sys.argv[2])
d=json.loads(src.read_text())
d["titleId"]="PPSA99006"
d["conceptId"]="99006"
d["contentId"]="UP9000-PPSA99006_00-REFROZENGLPROBE1"
d["contentVersion"]="01.000.000"
d["localizedParameters"]["defaultLanguage"]="en-US"
d["localizedParameters"]["en-US"]["titleName"]="reFrozen PS5 Graphics Probe"
dst.write_text(json.dumps(d, indent=2)+"\n")
PY

# Build the import stubs exactly like the upstream registered OpenGL gates.
mkdir -p "$APP/build/native-imports"
cp "$SDK/target/lib/libSceVideoOut.so" "$APP_SDK/target/lib/libSceVideoOut.so"
PS5_PAYLOAD_SDK="$APP_SDK" sh "$APP/tooling/prospero-clang18" \
  -std=c11 -O2 -fPIC -ffunction-sections -fdata-sections \
  -c "$GLROOT/native-app/agc_link_stub.c" -o "$APP/build/native-imports/agc_link_stub.o"
"$APP_SDK/bin/prospero-lld" --shared -soname libSceAgc.prx \
  -o "$APP_SDK/target/lib/libSceAgc.so" "$APP/build/native-imports/agc_link_stub.o"
PS5_PAYLOAD_SDK="$APP_SDK" sh "$APP/tooling/prospero-clang18" \
  -std=c11 -O2 -fPIC -ffunction-sections -fdata-sections \
  -c "$GLROOT/native-app/agc_driver_link_stub.c" -o "$APP/build/native-imports/agc_driver_link_stub.o"
"$APP_SDK/bin/prospero-lld" --shared -soname libSceAgcDriver.prx \
  -o "$APP_SDK/target/lib/libSceAgcDriver.so" "$APP/build/native-imports/agc_driver_link_stub.o"

compiler="${PS5_CLANG:-clang-18}"
compiler_runtime="$("$compiler" --print-resource-dir)/lib/linux/libclang_rt.builtins-x86_64.a"
for lib in \
  "$GLSDK/lib/libPS5OpenGL.a" \
  "$APP_SDK/target/lib/libunwind.a" \
  "$APP_SDK/target/lib/libc++abi.a" \
  "$APP_SDK/target/lib/libc++.a" \
  "$compiler_runtime"; do
  [[ -s "$lib" ]] || { echo "missing title link input: $lib" >&2; exit 2; }
done
group="$APP/vendor/libps5_opengl_group.a"
{
  printf 'SEARCH_DIR("%s")\n' "$APP_SDK/target/lib"
  printf 'SEARCH_DIR("%s")\n' "$GLSDK/lib"
  printf 'EXTERN(ps5_agc_gate2_run)\n'
  printf 'GROUP (\n'
  printf '  "%s"\n' "$GLSDK/lib/libPS5OpenGL.a"
  printf '  "%s"\n' "$APP_SDK/target/lib/libunwind.a"
  printf '  "%s"\n' "$APP_SDK/target/lib/libc++abi.a"
  printf '  "%s"\n' "$APP_SDK/target/lib/libc++.a"
  printf '  "%s"\n' "$compiler_runtime"
  printf ')\n'
} > "$group"
printf 'APP_INCLUDE_PATHS = include\nAPP_STATIC_ARCHIVES = vendor/libps5_opengl_group.a\n' > "$APP/.env"

PS5_CLANG="$compiler" BUILD_JOBS="${BUILD_JOBS:-2}" USE_CCACHE="${USE_CCACHE:-0}" \
  make -C "$APP" --no-print-directory app

DIST="$APP/dist/$TITLE"
for file in eboot.bin sce_module/libc.prx sce_sys/param.json; do
  [[ -s "$DIST/$file" ]] || { echo "missing packaged title file: $file" >&2; exit 1; }
done
grep -aFq "REFROZEN_PS5_WGL_TITLE pass=%d" "$APP/build/eboot.elf"
sha256sum "$DIST/eboot.bin" "$DIST/sce_module/libc.prx" > "$APP/build/title-sha256.txt"
printf 'reFrozen native WGL title: %s\n' "$DIST"
cat "$APP/build/title-sha256.txt"
