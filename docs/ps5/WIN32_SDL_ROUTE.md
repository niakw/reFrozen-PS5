# Warcraft III 1.26a Win32 runtime — SDL route for public PS5 builds

Status: **architecture chosen; implementation staged and not yet hardware-qualified**.

## Why SDL3 cannot be our public PS5 foundation

The pinned SDL3 3.4.8 source in the Encore vendor tree explicitly documents that
its PS5 port lives in a separate repository available to Sony NDA developers.
That backend is therefore not a public homebrew dependency we can rely on.

By contrast, the vendor tree also carries a reproducible **public SDL2 PS5**
integration based on `ps5-payload-dev/SDL` 2.30.12 commit
`8c56053f13ca13a0c050de613706ff69eb615836`. Encore's OpenGL integration
already documents a native PS5 video path and PS5 joystick corrections around
that source.

This project must not pretend SDL2 and SDL3 are ABI-compatible. The x86recomp
runtime currently calls SDL3. We will adapt only the actually required surface.

## Measured SDL3 surface

The PS5 object-closure job maps unresolved symbols **per source object**. The
current baseline is exactly **61 unique SDL symbols** across the 55 compilable
Win32 runtime units. CI fails if this count changes before the map is reviewed.

The map is metadata only; it contains no Warcraft code or assets.

## Staged replacement plan

1. **Window / display / event ownership**
   - Reuse the public PS5 SDL2 video backend concepts already integrated with
     the PS5 OpenGL/EGL stack.
   - Do not expose SDL2 objects directly to code compiled against SDL3 types.
   - Add a narrow host adapter and translate the required window/display/event
     operations explicitly.
   - One fixed fullscreen native window first; no fake resize/minimize semantics.

2. **Gamepad / input**
   - Reuse the public SDL2 PS5 joystick driver behavior, including native
     `scePad` ownership and reconnect handling.
   - Translate only the SDL3 gamepad operations actually used by the Win32 HLE.
   - Keyboard/mouse functions that have no qualified PS5 equivalent must either
     be mapped from DualSense/virtual input deliberately or report unsupported;
     they must not silently succeed.

3. **Audio**
   - Do **not** route the SDL3 audio-stream ABI through SDL2.
   - Implement the required host audio queue against the existing
     `sceAudioOut` adapter and preserve the Win32 Miles/DirectSound timing
     semantics above it.
   - The SDL3 audio symbols should disappear from the runtime closure once this
     adapter is wired.

4. **SDL_Renderer / surfaces**
   - These calls are not the Warcraft 3D renderer. They are host utility paths
     such as surfaces/textures/UI diagnostics.
   - Keep them separate from the OpenGL guest renderer. Implement only after
     the per-object import map identifies which startup/runtime paths require
     them.

5. **Timing / init / errors**
   - Replace trivial SDL timing/init helpers with platform-neutral or PS5
     services where that removes a dependency cleanly.
   - Preserve observable failure behavior and error reporting.

## Acceptance order

The SDL dependency is considered closed only when:

- the object import map contains **zero unresolved SDL3 symbols**;
- each replacement has host contract tests;
- the whole Win32 runtime still produces one valid PS5 x86-64 relocatable
  object;
- a registered PS5 title proves window creation, input delivery, audio queue,
  and clean shutdown;
- only then is the private Warcraft-generated C++ linked against the runtime.

The existing Win64 WGL probe does not qualify this Win32 SDL route.

## Source provenance

- SDL3 PS5 availability note:
  `sources/eden-cpm/sdl3/release-3.4.8/docs/README-ps5.md`
- Public PS5 SDL2 integration:
  `sources/opengl-source/integration/SDL2/README.md`
- Public PS5 SDL2 integration recipe:
  `sources/opengl-source/integration/SDL2/CMakeLists.txt`
- Public joystick correction:
  `sources/opengl-source/integration/SDL2/ps5-joystick.patch`

All are pinned in `niakw/Prospero.Eden-Encore-vendor` at
`1e51d1f3383f149a599e36052aba7d887d4b1f77`.
