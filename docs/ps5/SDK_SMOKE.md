# PS5 SDK — compile-only smoke gate

Status: **validated with the official public PS5 Payload SDK v0.42** on GitHub Actions, 18 November 2026. This is a real Prospero cross-compilation gate, not a linked PS5 application or device test.

## Origin and purpose

The fork's small CMake toolchain derives its Clang 18 target/sysroot/C++ settings from `niakw/ProsperoEden-Encore/tools/ps5.cmake` and the official Payload SDK wrappers. It compiles the host-independent guest-layout/memory contracts plus the native PS5 reservation/backing/mapping/probe adapters into x86-64 Prospero **objects**, without linking, launching or packaging Warcraft.

This preflight detects incompatible PS5 headers, target triples and C++20 source assumptions before native linking. It does **not** by itself qualify runtime syscalls, graphics, audio, input, Win32 APIs or game compatibility.

## Pinned public SDK

CI downloads the official release asset:

- project: `ps5-payload-dev/sdk`
- release: `v0.42`
- asset: `ps5-payload-sdk.zip`
- SHA-256: `8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da`

The digest matches the SDK pin already used by Encore. The archive must provide `target/include`, libc++ headers and `bin/prospero-clang`.

## Run on a prepared build host

```sh
export PS5_PAYLOAD_SDK=/path/to/ps5-payload-sdk
bash scripts/ps5/compile-guest32-object.sh
```

Outputs stay under git-ignored `build/ps5-sdk-smoke/`. The script refuses to run when the SDK or LLVM 18 tools are missing.

## What CI now proves

Run: https://github.com/niakw/refrozen_ps5/actions/runs/44219929718

- the official SDK archive passed its pinned SHA-256 check;
- CMake identified Clang 18.1.3;
- generated compile commands use the explicit `--target=x86_64-sie-ps5` target (the workflow asserts this);
- guest32/guest64 layout objects compile;
- exact-reservation, PE materializer, direct-backing and composed mapping contracts compile;
- native PS5 adapters for exact reservation, direct backing, composed mapping and the synthetic guest-memory probe compile;
- `llvm-readobj-18` reports x86-64 ELF objects;
- no game binaries, keys or translated Warcraft code are involved.

The public workflow preserves only text compiler/CMake evidence for a short retention period.

## What this does not prove

- no ELF has yet been linked in this gate;
- `sceKernelReserveVirtualRange`, direct-memory mapping and teardown have not yet been exercised by this repository on real PS5 hardware;
- no Warcraft executable has been lifted or compiled here.

## Next acceptance gate

Use the SDK's own `prospero-clang++` / `prospero-lld` wrapper to link a tiny synthetic PS5 ELF containing the already-compiled guest-memory probe. Inspect its ELF/import metadata in CI. Device execution of that synthetic ELF is the gate after native linking.
