# PS5 recompilation — initial architecture and evidence register

Date: 2026-11-18. Status: **research / NOT YET PORTED**.

## Goal
A PS5-native **static recompilation**, not Wine, of the user's own Warcraft III: Reign of Chaos and The Frozen Throne binaries. Preserve original gameplay and custom-map support, with optional visual enhancements and community network integration after compatibility work.

## Version policy
- **1.26a:** the only proven reFrozen recompiler input. Use as a *technical reference and validation oracle*, **not** as an automatic final product choice.
- **1.29.2 Legacy / 1.28.5 / 1.31.1:** candidate historical compatibility targets. Each requires independently verified executable hashes, instruction-set/ABI analysis, symbol reconstruction, recompilation and tests. No claim of interchangeable protocol or map support.
- Do **not** silently select a version by filename alone. The launcher should eventually map each user-provided install to an exact version and hash.
- Existing reFrozen 1.26a generated code or absolute function addresses must **not** be reused against 1.29/1.31 binaries.

## Current public-source evidence
- reFrozen CMake: compiled C++20 generated from eleven 32-bit Win32 PE modules through x86recomp and a custom runtime; `recomp_runtime` / `recomp_opengl`.
- `scripts/lift.sh`: pinned 1.26a symbols and manifests, hardcoded Homebrew Python/LLVM paths.
- `src/main.cpp`: native launcher and game configuration; macOS dynamic module route uses `dlopen`, `dlsym`, `.dylib` and Application Support location.
- `src/replaced.cpp`: version-specific function addresses; never generalize these across binary versions.
- Current upstream supports Mac ARM64; this fork has **no verified PS5 executable or runtime**.

## Minimal portability boundaries
1. **Guest executable and lifter**: Win32 32-bit addressing semantics; lift emitted C++ on a host compiler; keep generated proprietary code outside Git.
2. **Runtime core**: guest address space, exceptions, callbacks, thread/timer semantics and DLL import conventions; host-independent tests first.
3. **Platform layer**: isolate path conventions, clocks, filesystem, memory allocations, input, networking and audio.
4. **Graphics**: retain original simulation and OpenGL guest semantics; investigate translation to the PS5-supported GPU stack; do not assume Encore's renderer can be dropped in.
5. **Assets/maps**: local user-owned MPQ and W3M/W3X. No Blizzard data in commits, CI or artifacts.
6. **Community**: LAN must be tested before any third-party community connector. External servers, protocols and client plugin assumptions remain unverified.

## First acceptance gates
- [x] Fork is at the exact upstream head at project initialization.
- [x] Branch-specific read-only portability inventory, no game files.
- [ ] Inventory CI green, output audited (regex matches are triage hints).
- [ ] Review PS5 SDK/runtime interfaces and Encore's reusable *platform* components by file and license.
- [ ] Add platform-neutral guest address-space and Win32 API contract tests.
- [ ] Compile a **small generated-code fixture** for native host x86-64, without original game data.
- [ ] Compile that fixture with the confirmed PS5 toolchain and inspect ELF/imports.
- [ ] Only then attempt the full game with user-owned files and console testing.

## Critical blockers / unknowns
- Exact PS5 homebrew SDK capabilities for the user's firmware and installed loader.
- Whether runtime guest 32-bit fixed-address mapping fits the PS5 process address-space constraints.
- Availability/licensing of a stable PS5 Vulkan/OpenGL translation path and SDL3 functionality.
- Compatibility of 1.29/1.31 x86/x64 binary layout with x86recomp (the existing 1.26a pipeline is not sufficient evidence).
- Cinematics/DirectShow remain incomplete upstream for at least one TFT campaign.
- No measurable performance target or multi-community compatibility claim until device evidence.

## Working rules
- No guest executable, CD key, generated C++ from game binaries, maps, MPQs or proprietary assets are committed or uploaded to public CI.
- All modifications on scoped branches and PRs; preserve upstream attribution and GPL obligations.
- Every compatibility claim requires test command, environment, binary version, artifacts/logs and observed result.
- Prefer small fast gates; no full PS5 rebuild until required prerequisites are ready.
- This report records **read-only static indicators**, not a completed SDK audit or a successful PS5 build.

## First automated probe
```sh
python3 -m unittest discover -s tests -p test_ps5_portability_inventory.py -v
python3 scripts/ps5_portability_inventory.py --output build/ps5-portability.json
```
