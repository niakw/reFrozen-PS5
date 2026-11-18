#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Fetch and verify the preserved PS5 OpenGL SDK 1.0.2 archive.
# No game data is read or uploaded by this script.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT=${1:-"$ROOT/build/ps5-opengl-sdk-1.0.2"}
ARCHIVE_URL=${REFROZEN_PS5_OPENGL_ARCHIVE_URL:-https://github.com/KernelForgeLabs/ps5-opengl-sdk-mirror/releases/download/sdk-v1.0.2/ps5-opengl-sdk-1.0.2.tar.gz}
ARCHIVE_SHA256=${REFROZEN_PS5_OPENGL_ARCHIVE_SHA256:-30d8e51dd062739b629346102be5932728ba714bc50b1bdcdf08306c8843d9a4}

case "$ARCHIVE_SHA256" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) echo "invalid OpenGL archive SHA-256" >&2; exit 2 ;;
esac
[[ ${#ARCHIVE_SHA256} -eq 64 ]] || { echo "OpenGL archive SHA-256 must be 64 hex chars" >&2; exit 2; }
command -v curl >/dev/null
command -v sha256sum >/dev/null
command -v python3 >/dev/null

rm -rf "$OUT"
mkdir -p "$OUT/download" "$OUT/extracted"
archive="$OUT/download/ps5-opengl-sdk-1.0.2.tar.gz"
curl --fail --location --retry 3 --retry-delay 2 "$ARCHIVE_URL" -o "$archive"
printf "%s  %s\n" "$ARCHIVE_SHA256" "$archive" | sha256sum --check --strict

python3 - "$archive" "$OUT/extracted" <<'PY'
import sys, tarfile
from pathlib import Path, PurePosixPath
archive=Path(sys.argv[1]); out=Path(sys.argv[2])
with tarfile.open(archive, "r:gz") as tf:
    members=tf.getmembers()
    if not members:
        raise SystemExit("OpenGL SDK archive is empty")
    for m in members:
        p=PurePosixPath(m.name)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit(f"unsafe archive member: {m.name}")
    tf.extractall(out, filter="data")
print(f"OPENGL_ARCHIVE_SAFE members={len(members)}")
PY

mapfile -t mk_files < <(find "$OUT/extracted" -type f -path "*/share/ps5-opengl/ps5-opengl.mk" -print)
[[ ${#mk_files[@]} -eq 1 ]] || { printf "expected one ps5-opengl.mk, found %s\n" "${#mk_files[@]}" >&2; exit 1; }
mk=${mk_files[0]}
prefix="$(cd "$(dirname "$mk")/../.." && pwd -P)"
manifest="$prefix/manifest.sha256"
[[ -f "$manifest" ]] || { echo "SDK manifest.sha256 missing" >&2; exit 1; }
(cd "$prefix" && sha256sum --check --strict manifest.sha256)

for required in \
  "$prefix/lib/libPS5OpenGL.a" \
  "$prefix/include/EGL/egl.h" \
  "$prefix/include/GL/gl.h" \
  "$prefix/share/ps5-opengl/ps5-opengl.mk"; do
  [[ -s "$required" ]] || { echo "missing OpenGL SDK file: $required" >&2; exit 1; }
done

mapfile -t license_files < <(find "$OUT/extracted" -type f \( -name LICENSE -o -name THIRD_PARTY_NOTICES.md -o -path "*/LICENSES/*" \) -print)
[[ ${#license_files[@]} -ge 2 ]] || { echo "OpenGL SDK archive license/notices inventory incomplete" >&2; exit 1; }

printf "%s\n" "$prefix" > "$OUT/prefix.txt"
printf "REFROZEN_PS5_OPENGL_SDK pass=1 version=1.0.2 sha256=%s files_manifest=%s licenses=%s\n" \
  "$ARCHIVE_SHA256" "$(wc -l < "$manifest" | tr -d " ")" "${#license_files[@]}" | tee "$OUT/receipt.txt"
echo "$prefix"
