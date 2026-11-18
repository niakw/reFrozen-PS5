# Local Warcraft binary triage -> PS5 runtime work queue

Status: tooling only. No user Warcraft binary has been uploaded or inspected in this repository.

## 1. Generate a local PE census

Run on the machine holding your own game files:

```sh
python3 scripts/ps5/pe_probe.py \
  "/path/to/Warcraft III.exe" \
  "/path/to/Frozen Throne.exe" \
  "/path/to/Game.dll" \
  --output build/private-war3-census.json
```

The report contains basename, SHA-256, PE32/PE32+, image metadata, section names and imported DLL/API names. It does not execute the binary, read a CD key, infer the patch from a timestamp, or include the local installation path.

**Keep the report private until reviewed.** API names and hashes are useful engineering evidence, but no reason exists to publish a user's local binary inventory by default.

## 2. Compare imports with the existing reFrozen HLE reference

```sh
python3 scripts/ps5/runtime_gap_report.py \
  build/private-war3-census.json \
  --output build/private-war3-runtime-gaps.json
```

Statuses:

- `reference_hle`: an exact DLL/API handler appears in reFrozen's current x86recomp patch set.
- `ordinal_needs_manual`: the import is by ordinal; resolution needs the exact DLL/version export table.
- `unmapped`: no exact current reFrozen HLE handler was found.
- `ps5_status=unverified`: **always** used until that service is compiled and exercised through the PS5 runtime.

A reference HLE is not automatically portable. For example, implementations may rely on Darwin/POSIX functions, Cocoa, macOS kqueue semantics or a host graphics/audio stack unavailable on PS5.

## 3. Turn the report into implementation batches

Recommended order:

1. **core/process/memory** — loader, VirtualAlloc/Free, threads, TLS, timers, files, synchronization.
2. **window/input** — message loop assumptions and controller/keyboard/mouse translation.
3. **graphics** — identify OpenGL/D3D/DXGI/Vulkan path before choosing an Encore bridge.
4. **audio/media** — Miles/DirectSound/WinMM/video codecs and campaign cinematics.
5. **network** — Winsock/LAN first; external community compatibility only after deterministic local/LAN behavior.
6. **unknown/vendor DLLs** — decide whether to lift the DLL, replace it natively, or implement a narrow ABI bridge.

For every API promoted to PS5-supported, require:
- a synthetic or public test fixture,
- host regression test,
- PS5 compile evidence,
- device execution/log evidence where the API has runtime effects.

## Current evidence

- reFrozen 1.26a Win32 remains the behavioral reference.
- Synthetic PE32/PE32+ parsing is tested.
- Synthetic Win64 code is statically translated, compiled, linked and executed on an x86-64 host in CI.
- 32-bit and 64-bit guest layout checks compile/run on Linux and macOS.
- The Encore-derived PS5 SDK object smoke path exists, but no SDK/device validation has yet been recorded in this repository.
