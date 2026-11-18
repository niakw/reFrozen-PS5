# Lifter selection for multiple Warcraft III Classic executable generations

Status: **architectural investigation**, 18 November 2026. No Warcraft III x64 binaries have been inspected or recompiled in this fork.

## Different code architectures require different lifters

| Input generation | Evidence | Candidate | Status |
| --- | --- | --- | --- |
| Warcraft III 1.26a (PE32, Win32) | reFrozen `scripts/lift.sh`, eleven modules and pinned manifest | reFrozen/x86recomp | Upstream playable on macOS ARM64; PS5 not validated |
| Legacy 1.29.2 | No user-owned executable inspected yet | Select only after `pe_probe.py` detects the exact machine and hash | Unknown |
| Historical 1.31.1 64-bit Windows client | Blizzard 1.31.0 notes added 64-bit support; actual user binary still needed | NightSight `recomp64.py` or pcrecomp `lift64_cpu.py` | Candidates, not integrated |

## New candidates examined

1. `NightSightProductions/Recomp-Framework` (MIT): Windows x86-64 PE → C using Capstone/LIEF. Its runtime is currently Apple Silicon/macOS-specific: Cocoa input/windows, CoreAudio and Metal/Vulkan translation. The *translator* might be portable; we cannot directly import its runtime as a PS5 replacement.
2. `sp00nznet/pcrecomp` (MIT): has `tools/lift/lift64_cpu.py`, `generate64.py`, `runtime/recomp64_cpu`; Win32HLE is documented for its 32-bit runtime, so a PS5-ready 64-bit Win32 service implementation is **not** established.
3. `reFrozen/x86recomp`: known 1.26a x86-32 inputs and established gameplay semantics; do not assume its lifter handles PE32+ Win64.

The MIT toolchain(s) can in principle coexist with the GPL-3.0-or-later project when their notices and obligations are preserved. No third-party code is vendored in the fork at this stage.

## Evidence gate (no game assets)

- Create a deterministic synthetic PE32+ file with `.text`, `.pdata`, `.xdata` and one tiny function (`mov eax, 42; ret`).
- Lift it using the **pinned** NightSight Win64 translator on a CI runner.
- Require generated C for the function, empty unsupported-instruction report, and compile that generated code to an x86-64 host object.
- Treat this as translator/compile feasibility only: Win64 ABI, memory mapping, imports, exceptions, game module dependencies and PS5 toolchain remain untested.
- Do not upload any user Warcraft executables or translated game output to GitHub.

## Next after synthetic gate

1. Get private SHA-256/PE metadata for the exact user-owned Classic build; check PE32/PE32+ and `.pdata` presence.
2. Audit the imports, exceptions, graphics API and content container formats, then decide which translator(s) are worth maintaining.
3. Test differential instruction semantics on native x86-64 host and any Win64 API shims against official test vectors.
4. Port selected runtime pieces to PS5 using the Encore SDK smoke target. Console performance and content compatibility must be measured later.

This matrix avoids anchoring a PS5 multiversion project to a 1.26a-only lifter.
