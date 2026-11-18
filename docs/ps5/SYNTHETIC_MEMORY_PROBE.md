# Synthetic PS5 guest-memory probe ELF

This is the first standalone PS5 executable produced by `refrozen_ps5`.
It contains **no Warcraft code or data**. Its only purpose is to qualify the
memory model required by a later static recompilation.

## What the ELF does on hardware

Default probe:

- guest base: `0x140000000`;
- logical image size: `0x5000`;
- PS5 rounded mapping: `0x8000`;
- direct-memory type: `12`;
- guest mapping: `PROT_READ | PROT_WRITE`, **not executable**;
- marker address: guest base + `0x2000`.

Runtime sequence:

```text
sceKernelReserveVirtualRange (exact VA)
    -> sceKernelAllocateDirectMemory
    -> sceKernelMapDirectMemory (MAP_FIXED)
    -> marker write/read
    -> munmap
    -> sceKernelReleaseDirectMemory
```

Expected success logs:

```text
REFROZEN_PS5_GUEST_PROBE pass=1 base=140000000 logical=5000 mapped=8000 marker=5743335053354d41
REFROZEN_PS5_MEMORY_PROBE_MAIN result=pass
```

If the mapping state reports `abort=1`, the process should be terminated:
the runtime intentionally refuses speculative cleanup when a kernel call leaves
virtual-address ownership ambiguous.

## Build locally

With the official Payload SDK available:

```sh
export PS5_PAYLOAD_SDK=/path/to/ps5-payload-sdk
bash scripts/ps5/build-memory-probe-elf.sh
```

Output:

```text
build/ps5-probe/refrozen-guest-memory-probe.elf
```

## Deploy to a PS5 payload listener

Using the SDK deploy helper, when the console's payload listener is available:

```sh
"$PS5_PAYLOAD_SDK/bin/prospero-deploy" \
  -h <PS5_IP> -p 9021 \
  build/ps5-probe/refrozen-guest-memory-probe.elf
```

The listener address/port depends on the user's homebrew environment; `9021`
is the SDK sample default, not a requirement of reFrozen.

## CI artifact

The `PS5 synthetic memory-probe ELF` workflow:

1. downloads the official Payload SDK v0.42;
2. verifies the pinned SDK SHA-256;
3. links through `prospero-clang++` / the official PS5 linker script;
4. verifies PIE x86-64 ELF metadata;
5. requires dynamic dependencies on:
   - `libkernel_web.sprx`
   - `libSceLibcInternal.sprx`
   - `libSceNet.sprx`;
6. requires unresolved runtime imports for the five `sceKernel*` memory
   primitives plus `munmap`;
7. rejects desktop Linux/FreeBSD interpreter paths;
8. rejects GitHub runner source-path leakage;
9. uploads the ELF, metadata and checksum as a short-lived Actions artifact.

The official Payload SDK v0.42 linker script currently marks its native text
`PT_LOAD` as RWE (flags `0x7`). That is SDK behavior and is separate from
the reFrozen **guest PE mapping**, which this project keeps non-executable.

## What a hardware pass unlocks

Once this ELF passes on the console, the next probe should use the same mapped
range to:

1. materialize the public synthetic Win64 PE;
2. invoke the already-validated translated Win64 function;
3. prove the guest `.data` mutation `41 -> 42`;
4. tear the mapping down.

Only after that synthetic PS5 chain is green should private user-owned Warcraft
modules enter the porting pipeline.
