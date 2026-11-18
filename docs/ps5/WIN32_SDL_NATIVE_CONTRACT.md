# Win32 SDL3 / graphics ownership for the 1.26a PS5 route

Date: 2026-11-18. This is source/link evidence, not console execution.

## 55-object unresolved baseline

The native PS5 x86recomp aggregate exposed **61 SDL3 unresolved symbols**.
The patched runtime source contains 126 direct SDL calls; 66 additional calls
are almost entirely the SDL_GPU implementation in `gfx/gpu_device.cpp`.

The 61-link-symbol baseline is partitioned into:
- core/time: 8;
- window/display/events: 27;
- gamepad: 8;
- audio stream: 7;
- auxiliary renderer/surface: 11.

Ownership is narrow:
- gamepad -> `hle/xinput.cpp`;
- audio -> `audio/mixer.cpp`, `hle/winmm_wave.cpp`;
- window/events -> `hle/user32_window.cpp`, `hle/user32_input.cpp`, `hle/dinput8.cpp`;
- GDI auxiliary renderer -> `hle/user32_window.cpp`, `hle/present.cpp`.

## SDL_GPU is not an independent first-launch requirement

The trace run `44323987997` found:
- `CreateGpuDevice` implementation: `gfx/gpu_device.cpp`;
- declaration: `gfx/device.h`;
- only factory call: `gfx/device.cpp`.

However, the Win32 OpenGL HLE cannot simply discard it. `wglMakeCurrent`
creates a `gl::Context`, and that context creates the backend via
`gfx::CreateChosenDevice`. Upstream's default chosen backend is
`Backend::Gpu` (SDL_GPU).

A direct scan of `runtime/gl/context.cpp` shows the guest OpenGL semantic
layer directly requires only these **11** `gfx::Device` operations:

`BeginScene`, `Clear`, `CreateDepth`, `CreateTexture`,
`DestroyDepth`, `DestroyTexture`, `DrawFf`, `ReadBack`,
`ResetSwapChain`, `SetRenderTarget`, `UpdateTexture`.

Therefore the preferred 1.26a route is **not** a 66-function fake SDL_GPU
shim. It is a PS5 OpenGL `gfx::Device` implementation that satisfies the
guest OpenGL contract using the now-qualified PS5 OpenGL 1.0.2 stack.
Unsupported D3D9/program/compute methods must remain explicit failures until
implemented.

This keeps SDL3 work focused on real host services (window/event/input/audio)
while replacing the GPU backend at its intended abstraction boundary.

## Hardware boundary

The registered `PPSA99006` title proves the PS5 OpenGL consumer can be
built and packaged in CI; hardware rendering still requires a console receipt.
A PS5 OpenGL `gfx::Device` implementation also needs its own device-level
tests before it is used with lifted Warcraft code.
