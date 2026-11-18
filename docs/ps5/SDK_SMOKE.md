# PS5 SDK — compile-only smoke gate

Status: **NOT YET RUN AGAINST A PS5 SDK**. This is a reproducible build recipe, not a working native game.

## Origin and purpose

The toolchain derives its Clang 18 target, sysroot and C++ flags from `niakw/ProsperoEden-Encore/tools/ps5.cmake` (GPL-3.0-or-later). It is intentionally small: it compiles the synthetic host-independent 32-bit guest-range fixture into an x86-64 ELF **object**, without linking, launching, or packaging a PS5 application.

This preflight can detect incompatible compiler headers, target triples, and C++20 compilation settings before building a custom runtime. A successful result **does not** qualify guest memory mapping, the Win32 API runtime, audio, graphics, threading or game compatibility.

## Requirements

- A host with `clang++-18`, `llvm-ar-18`, `llvm-ranlib-18`, `llvm-readobj-18` and CMake 3.25+.
- The same PS5 payload SDK layout expected by Encore, made available **locally** via `PS5_PAYLOAD_SDK`, including `target/include` and `target/include/c++/v1`.
- No game files, keys, generated code, GitHub secrets or PS5 are required for the smoke check.

## Run on a prepared build host

```sh
export PS5_PAYLOAD_SDK=/path/to/your/local/sdk
bash scripts/ps5/compile-guest32-object.sh
```

Outputs stay in git-ignored `build/ps5-sdk-smoke/`; read `object-header.txt` to confirm x86-64 ELF. The script exits with a clear error if the SDK/tools are absent. No binary data is uploaded anywhere.

## What CI currently proves

- Host C++20 unit tests run as an executable on Linux and macOS.
- The **object-only mode** compiles on Ubuntu without depending on Warcraft binaries.
- The PS5 SDK command refuses to run without a locally supplied SDK.
- CI **does not** cross-compile the fixture with a PS5 SDK, because one is not provisioned to the runner.

## Next acceptance gate

Run the SDK smoke on a known-good private build host; preserve the compiler triple, toolchain version and ELF header output. Then compare against Encore's actual SDK configuration before attempting to port x86recomp's guest memory reserve/commit functionality. Only real device testing can validate the PS5 runtime.

