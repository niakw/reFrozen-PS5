# Registered PS5 WGL/OpenGL title probe — PPSA99006

Status: **build recipe prepared; hardware execution not yet qualified**.

This is the first reFrozen graphics probe intended to run as a managed native
PS5 title rather than through a raw ELF loader.

## Identity

- Title ID: `PPSA99006`
- Concept ID: `99006`
- Content ID: `UP9000-PPSA99006_00-REFROZENGLPROBE1`
- Title: `reFrozen PS5 Graphics Probe`

The ID is distinct from the vendored OpenGL gate (`PPSA99005`) and Encore
(`PPSA99008`).

## What it executes

The title uses the production reFrozen `EglWglBackend` and `WglRegistry`:

1. create an OpenGL **Compatibility** context;
2. make it current on the fullscreen PS5 EGL surface;
3. query `GL_VERSION` and `GL_RENDERER`;
4. configure legacy projection/modelview matrices;
5. render a colored `GL_QUADS` primitive with immediate-mode
   `glBegin/glColor/glVertex/glEnd`;
6. present 120 frames through `WglRegistry::SwapBuffers`;
7. verify `glGetError() == GL_NO_ERROR`;
8. clear current and destroy the context;
9. emit a bounded receipt:
   `REFROZEN_PS5_WGL_TITLE pass=...`.

The visible frame deliberately uses old fixed-function behavior because that is
a more useful Warcraft Classic compatibility proof than a modern shader-only
triangle.

## Packaging lineage

`scripts/ps5/build-native-wgl-title.sh` requires:

- public Payload SDK v0.42;
- the manifest-verified installed PS5 OpenGL SDK from the real-SDK gate;
- the pinned Encore vendor OpenGL source root;
- the pinned vendored native boilerplate
  `4f531c4b517f80bcb6b1267135848168d2250047`.

It mirrors the upstream hardware-gate integration:

- native OpenGL `ps5-pie.ld` and export map;
- `app_heap.c` and `runtime_shims.c`;
- 256 MiB module heap declaration;
- malloc/calloc/realloc/free/posix_memalign/malloc_usable_size wraps;
- AGC and AGC-driver import stubs;
- static OpenGL archive group plus libc++/unwind/compiler runtime;
- folder-title signing and assembly.

Raw `elfldr` execution is intentionally out of scope for this graphics gate.

## Acceptance

A successful CI package proves only that the title folder is reproducible and
self-consistent. Hardware qualification requires the user to install/register
`PPSA99006`, run it on the PS5, and provide the resulting
`/download0/ps5-opengl.log` receipt.

Only a hardware receipt with `REFROZEN_PS5_WGL_TITLE pass=1` plus the exact
`eboot.bin` SHA-256 qualifies this graphics route for the later private
Warcraft Classic lift.
