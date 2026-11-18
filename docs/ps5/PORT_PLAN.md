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
- [x] Inventory CI green on the research PR; regex results are triage hints, not a runtime audit.
- [x] Initial source-level Encore reuse candidate list (`ENCORE_REUSE.md`); SDK integration and license checks remain open.
- [x] Add platform-neutral 32-bit guest image-range bounds/overlap tests; compiled on Linux/macOS.
- [x] Add exact guest-address/mapping contracts and synthetic PS5 memory/link probes for the Win64 candidate; the original 1.26a x86recomp path remains separately version-specific.
- [x] Compile a synthetic C++20 host fixture on Linux and macOS with strict warnings.
- [x] Compile actual Win64 lifter-generated code from synthetic PE fixtures and execute/inspect the translated import/memory/WGL chains without original game data.
- [x] Cross-compile/link synthetic translated fixtures with Payload SDK v0.42 and inspect x86-64 PS5 ELF/import evidence.
- [ ] Qualify the registered reFrozen WGL/OpenGL probe on real PS5 hardware, then audit and lift the user's exact Warcraft Classic files privately.

## Local user-owned binary architecture probe

Run `python3 scripts/ps5/pe_probe.py /path/to/war3.exe /path/to/Game.dll` locally when files become available. The script outputs PE machine, PE32/PE32+, image base, sections, SHA-256 and file basename; it does **not** read CD keys, execute code, upload files, or infer a Warcraft patch version without a validated hash catalog. CI uses only synthetic PE fixtures. Logs should not include full local install paths.

## Current PS5 port state — 2026-11-18

- Win64 candidate runtime: **21/23 C translation units compile for PS5**. The only compiler-red upstream units are the macOS Steam bridge and macOS Vulkan loader; neither is in the selected first offline/LAN OpenGL route.
- Native audio: XAudio2 and WASAPI route through the PS5 `sceAudioOut` bridge.
- Input/display: DirectInput, display and user32 no longer depend on CoreGraphics/AppKit for the PS5 build.
- Crypto: bcrypt/CommonCrypto is adapted to the pinned PacBrew OpenSSL family and has host semantic tests plus PS5 compiler evidence.
- Graphics: synthetic Win64 guest WGL calls already reach the reFrozen WGL registry/EGL backend. PR #55 is the exact audited PS5 OpenGL SDK link gate; PR #60 packages the registered `PPSA99006` hardware probe.
- Private-game audit: `scripts/ps5/private-install-runtime-audit.sh` scans user-owned PE files locally, reports architecture/import/runtime gaps and feeds a fail-closed first-launch gate without uploading game bytes.
- **No Warcraft executable has yet been lifted in this repository and no reFrozen graphics probe has yet been qualified on the user's PS5.**

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
