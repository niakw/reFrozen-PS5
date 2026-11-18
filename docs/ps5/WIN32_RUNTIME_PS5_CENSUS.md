# Warcraft III 1.26a Win32 runtime → PS5 compiler census

Status: **compiler/source evidence, not device qualification**  
Date: 2026-11-18

## Scope

The exact private Warcraft input is PE32/x86 build `1.26.0.6401`, so the first functional port uses reFrozen's patched **x86recomp Win32 runtime**, not the separate Win64 research runtime.

Pinned inputs:

- x86recomp/SwARc base: `ad1b16b30b3cc049e47a1ebbf96e8066b32191e1`
- reFrozen patches: `0001`–`0029` on this branch
- Payload SDK: public v0.42, SHA-256 `8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da`
- compiler target: `x86_64-sie-ps5`

No Warcraft binary or generated game code is used by the public compiler census.

## Source census before PS5-specific patch 0029

After applying reFrozen patches 0001–0028:

- runtime source/header files scanned: **105**
- files with obvious Apple/Darwin lexical dependencies: **3**
- files without those markers: **102**

The three candidates were:

```text
platform.cpp
process.cpp
stall.cpp
```

This lexical classification was intentionally conservative. It did not claim the other 102 files compile for PS5.

Evidence: Actions run `44291365664`.

## Real Payload SDK compile probe

Initial direct compile with `prospero-clang++`:

| Unit | Initial result | First blocker |
| --- | --- | --- |
| `platform.cpp` | FAIL | Linux-only `<sys/prctl.h>` |
| `process.cpp` | FAIL | `MAP_NORESERVE` is not exposed by Payload SDK |
| `stall.cpp` | PASS | — |

Evidence: run `44291679213`, job `134758186142`.

## Patch 0029

`0029-runtime-ps5-freebsd-host-portability.patch` makes two host assumptions conditional:

1. `<sys/prctl.h>` and `PR_SET_TIMERSLACK` are used only on Linux.
2. `MAP_NORESERVE` is added to the main guest-stack mapping only when the host provides it.

The monotonic-clock and absolute `clock_nanosleep` path remains unchanged for non-Apple POSIX hosts. The main-stack allocation remains anonymous/private and still fails closed if `mmap` fails.

After patch 0029, the same real SDK probe reports:

```text
platform.cpp  PASS
process.cpp   PASS
stall.cpp     PASS
```

Evidence: Actions run `44292190192`, job `134759925532`.

## Interpretation

This proves that the first explicit host-platform blockers in the PE32 runtime can compile for the public PS5 Payload SDK with a very small portability correction.

It does **not** prove:

- guest memory/fault delivery works correctly on hardware;
- `ucontext` stack switching or signal-context extraction is complete for PS5;
- SDL3 window/input/audio is available on this homebrew toolchain;
- x86recomp's SDL_GPU graphics device is usable on PS5;
- OpenGL HLE renders Warcraft correctly;
- generated Warcraft C++ links or runs on PS5.

The official SDL3 PS5 platform implementation is not part of the public SDL source used here. The project therefore must not assume that an upstream SDL PS5 backend is available. Host-facing SDL dependencies will be isolated or replaced with public/native PS5 adapters.

## Next compiler gate

Compile **every C++ translation unit under the patched runtime** with the real Payload SDK in syntax/object-probe mode. Supply pinned SDL3 **headers only** where a unit needs type declarations, without claiming an SDL PS5 implementation or linking SDL.

The resulting failures will be classified into:

1. POSIX/FreeBSD/PS5 portability;
2. SDL host-window/input/audio dependencies;
3. graphics-device/build-generated dependencies;
4. third-party headers/libraries;
5. actual C++/ABI incompatibilities.

Only after that census should production host adapters be changed.
