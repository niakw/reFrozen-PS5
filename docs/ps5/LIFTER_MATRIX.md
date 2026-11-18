# Lifter selection for multiple Warcraft III Classic executable generations

Status: **synthetic Win64 path proven / real Warcraft input pending**, 18 November 2026. No user-owned Warcraft III x64 binary has yet been inspected or recompiled in this repository.

## Different code architectures require different lifters

| Input generation | Evidence | Candidate | Status |
| --- | --- | --- | --- |
| Warcraft III 1.26a (PE32, Win32) | reFrozen `scripts/lift.sh`, eleven modules and pinned manifest | reFrozen/x86recomp | Upstream playable on macOS ARM64; PS5 not validated |
| Legacy 1.29.2 | No user-owned executable inspected yet | Select only after `pe_probe.py` detects the exact machine and hash | Unknown |
| Historical 1.31.1 64-bit Windows client | 64-bit client generation; exact user binary/hash still needed | pinned NightSight `recomp64.py` + PS5 runtime adaptations | Synthetic PE64 lift, import dispatch and PS5 ELF chain proven; real game pending |

## New candidates examined

1. `NightSightProductions/Recomp-Framework` (MIT): Windows x86-64 PE → C using Capstone/LIEF. The translator is now exercised by this fork on deterministic PE64 fixtures. Its original macOS runtime has been selectively adapted: the PS5 compile census is 21/23 units, with native display/input/audio/crypto paths; its Steam and macOS Vulkan units remain outside the selected Warcraft OpenGL route.
2. `sp00nznet/pcrecomp` (MIT): has `tools/lift/lift64_cpu.py`, `generate64.py`, `runtime/recomp64_cpu`; Win32HLE is documented for its 32-bit runtime, so a PS5-ready 64-bit Win32 service implementation is **not** established.
3. `reFrozen/x86recomp`: known 1.26a x86-32 inputs and established gameplay semantics; do not assume its lifter handles PE32+ Win64.

The MIT toolchain(s) can in principle coexist with the GPL-3.0-or-later project when their notices and obligations are preserved. No third-party code is vendored in the fork at this stage.

## Evidence gate (no game assets)

- [x] Create deterministic synthetic PE32+ fixtures with `.text`, `.pdata`, `.xdata` and controlled imports/instructions.
- [x] Lift them using the **pinned** NightSight Win64 translator on CI.
- [x] Compile generated C, execute synthetic import chains, and link translated code into x86-64 PS5 ELF fixtures with Payload SDK v0.42.
- [x] Exercise synthetic memory mapping and WGL import dispatch through PS5-facing contracts.
- [ ] Qualify the registered WGL/OpenGL title on hardware and inspect the exact user-owned Warcraft PE set before claiming game compatibility.
- Do not upload any user Warcraft executables or translated game output to GitHub.

## Next after synthetic gate

1. Finish PR #55/#60 and require a real PS5 WGL/OpenGL hardware receipt.
2. Run the merged private install audit on the exact user-owned Classic build; record SHA-256, PE32/PE32+, imports, COM markers and runtime gaps without uploading binaries.
3. Lift only the architecture/version actually supplied; keep generated game C under ignored local/private paths.
4. Compile/link the first private Warcraft PS5 candidate and close only the imports/instructions actually observed.
5. Validate startup, menu, solo gameplay, RoC/TFT campaigns, saves, custom maps and LAN before graphics enhancements or community-service integration.

This matrix avoids anchoring a PS5 multiversion project to a 1.26a-only lifter.
