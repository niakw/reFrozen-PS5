# Encore PS5 reuse candidates — source inspection (2026-11-18)

This is a **source-level candidate list**, not a proven import or console test.

| Encore file | Observed | Action for reFrozen |
| --- | --- | --- |
| [headless/vulkan_surface.cpp](https://github.com/niakw/ProsperoEden-Encore/blob/main/headless/vulkan_surface.cpp) | Uses PS5 window-system discriminator, Vulkan display enumeration and `vkCreateDisplayPlaneSurfaceKHR` | Extract concepts into a *renderer-neutral* PS5 surface adapter after validating PS5 Vulkan availability; do not copy Eden's `EmuWindow` or Vulkan wrapper dependencies directly. |
| [headless/inject.cmake](https://github.com/niakw/ProsperoEden-Encore/blob/main/headless/inject.cmake) | Native `PS5_NATIVE` feature disables Linux SDL audio/window subsystems, uses native PS5 input/audio | Reuse configuration principles, then verify which SDL3 services reFrozen actually uses. |
| [docs/PS5_NATIVE_ARCHITECTURE.md](https://github.com/niakw/ProsperoEden-Encore/blob/main/docs/PS5_NATIVE_ARCHITECTURE.md) | Documents memory, CPU affinity, native GPU, frame pacing and qualification constraints | Adopt measurement/qualification methodology; not evidence that the runtime APIs are directly portable. |
| [headless/CMakeLists.txt](https://github.com/niakw/ProsperoEden-Encore/blob/main/headless/CMakeLists.txt) | Console frontend build entry | Audit actual SDK/toolchain and package/link rules before extracting a minimal CMake toolchain file. |

## Immediate choices
1. **No vendor/Encore source copied in this PR.** License and build dependencies must be reviewed before code reuse.
2. A plain Vulkan surface is not an OpenGL renderer. reFrozen's `recomp_opengl` requires an OpenGL translation approach or a newly validated renderer backend.
3. Platform code can be modularized independently of Warcraft 1.26a / 1.29.x / 1.31.x lifter work.
4. Graphics options and community integration are out of scope for the first reproducible host/PS5 fixture.

## Port gate
A demonstrable minimal PS5 project must create a window/surface, present a frame and cleanly shut down before wiring reFrozen guest graphics into it. Do not claim supported 60/120 Hz just because a mode appears in a source file.
