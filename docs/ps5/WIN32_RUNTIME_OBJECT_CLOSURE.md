# Win32 x86recomp runtime → native PS5 object closure

Status: **compiler/linker qualification only; no Warcraft game object or console execution**.

## Motivation

The user-owned 1.26a Warcraft III installation uses a PE32/x86 guest, lifted
through reFrozen's patched x86recomp. The separate NightSight Win64 runtime
cannot substitute for this Win32 HLE ABI.

The earlier Payload SDK v0.42 source census compiled **55/63** of the patched
x86recomp C++ runtime translation units with `-fsyntax-only`. An initial real
compiler/linker gate then compiled nine essential units and produced a
relocatable x86-64 object with **286 unresolved-symbol lines** (run
`44313480595`).

Those undefined symbols included the unlinked `recomp::gl::Context`
implementation, other runtime units and libc++/host services; this is not a
claim that 286 independent reimplementations are needed.

## New closure gate

The dedicated script `scripts/ps5/compile-win32-runtime-closure.sh` consumes
the actual, pinned compiler-census TSV. For all units with a PASS result, it:

1. invokes `prospero-clang++` on every public source file (no game code);
2. records object compilation failures rather than hiding them;
3. requires at least 55 successful object builds;
4. joins those objects into a single relocatable PS5 x86-64 ELF object with
   `ld.lld-18 -r`;
5. preserves defined/undefined symbol inventories for the next dependency
   closure, plus ELF machine metadata.

The script cannot run without the pinned PS5 Payload SDK v0.42 and patched
runtime; it never reads Blizzard files. It does not link libc++, SDL3,
FFmpeg, SoftFloat, OpenGL PS5 or a game executable.

## Outstanding before a native Warcraft 1.26a launch

- Port/resolve missing SDK-compatible dependencies and their actual implementations,
  rather than substituting permissive stubs.
- Integrate the true Win32 `recomp::gl::Context` and fixed-function rendering
  semantics with the already investigated PS5 OpenGL backend. The Win64 WGL
  probe alone does not validate the Win32 OpenGL HLE.
- Qualify guest memory reservations, exception delivery, threaded callbacks,
  audio, input and sockets at runtime on console.
- Generate/compile all real lifted game C++ **only in a controlled private
  environment**, then link the user-owned 1.26a game against the PS5 Win32
  runtime and inspect its actual imports.
- Verify the real MPQ LFS contents and run the original RoC/TFT scenarios and
  legacy maps. No historical custom-map compatibility claim is made yet.

A passing relocatable object is a useful linker smoke test, not a complete
PS5 payload or playable game.
