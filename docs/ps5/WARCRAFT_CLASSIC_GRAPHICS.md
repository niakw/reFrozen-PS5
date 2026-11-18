# Warcraft III Classic PS5 graphics route

Status: architecture gate. No Warcraft binary has been committed or executed.

## Evidence behind the initial route

Blizzard's Warcraft III 1.31.0 notes state that the Windows client gained 64-bit
support and Direct3D 11, while the command line retained explicit renderer
selection through `-graphicsapi Direct3D9` and `-graphicsapi OpenGL`.

Official reference:
https://us.forums.blizzard.com/en/warcraft3/t/1-31-0-patch-notes/5721

This does **not** prove that every 1.31.1 executable statically imports
`opengl32.dll`: renderer DLLs can be selected and loaded dynamically.

## Project policy

1. Inspect the user's exact executable locally with `scripts/ps5/pe_probe.py`.
2. Record PE32/PE32+, exact SHA-256 and static graphics imports.
3. For the first 1.31.x PS5 execution attempt, prefer Blizzard's supported
   `-graphicsapi OpenGL` route rather than implementing D3D11 first.
4. Do not remove D3D11 support from the project design. It remains a later
   compatibility route if a target build/map needs it.
5. Never infer an active renderer from `dxgi.dll` alone or from a patch
   version alone.

## Why OpenGL first

Encore already has a PS5-native EGL/OpenGL path backed by the reviewed
`ps5-opengl` stack. Encore pins source commit
`ad2807d41cef2681882a9ee0d20808779f74b7cd` and creates an OpenGL 4.6 Core
EGL context on the PS5 display.

reFrozen's 1.26a runtime also deliberately selects Warcraft III's OpenGL
renderer and has extensive compatibility work for Warcraft's older OpenGL
semantics. These are useful *behavioral references*; they are not drop-in code
for the Win64 client.

The intended 1.31.x path is therefore:

```
Warcraft III Classic Win64 guest
        |
        | -graphicsapi OpenGL
        v
opengl32.dll / WGL compatibility layer
        |
        | WGL handles, pixel format, contexts, SwapBuffers,
        | wglGetProcAddress, legacy GL compatibility where required
        v
PS5 EGL + OpenGL implementation
        |
        v
PS5 display
```

## Separation of responsibilities

### Guest/WGL compatibility

Owns Windows-visible HGLRC/HDC behavior, pixel-format queries, current-context
state, proc lookup and SwapBuffers semantics. This layer must remain testable
without a PS5.

### PS5 EGL platform

Owns `eglGetDisplay`, display mode selection, EGL initialization, surface and
context creation, make-current, swap interval and presentation. It must not
contain Warcraft simulation or game-specific rules.

### Legacy OpenGL compatibility

Do not assume OpenGL 4.6 Core alone is enough. Warcraft Classic may use
fixed-function/compatibility calls depending on version and renderer path.
The exact user binary plus runtime traces determine which calls are needed.
reFrozen's tested GL 1.1/fixed-function implementation is the reference for
semantics where applicable.

### Video enhancements

Resolution, refresh rate, anisotropic filtering, AA/post-AA, upscale and later
frame-generation experiments live above/beside presentation. They must never
change Warcraft simulation timing or map logic.

## First graphics acceptance gates

- [x] Exact local PE probe can identify architecture/imports without executing
      proprietary code.
- [x] PS5 exact guest memory/runtime core builds independently of graphics.
- [ ] PE probe reports a conservative graphics-route classification.
- [ ] Build a synthetic WGL contract fixture: create context, make current,
      proc lookup, swap, destroy.
- [ ] Compile PS5 EGL adapter against the same pinned OpenGL source/profile
      used by Encore.
- [ ] Link a synthetic PS5 OpenGL ELF and present a frame.
- [ ] Only after the user's Classic binary is inspected, enable the Warcraft
      profile's `-graphicsapi OpenGL` argument and translate its real imports.
- [ ] Test menus, one campaign mission and a representative custom map before
      adding visual enhancements.

## Explicit non-goals for this stage

- No D3D11 reimplementation.
- No claim that a 1.31.1 game build already reaches the PS5 renderer.
- No bundling of Warcraft executables, MPQs, maps or translated game C.
- No assumption that every historical custom map requires the same renderer.
