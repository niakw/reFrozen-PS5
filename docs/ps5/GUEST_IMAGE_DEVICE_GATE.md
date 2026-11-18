# PS5 synthetic guest-image device gate

Status: implementation + host tests/object compilation. **Not yet executed on a real PS5 from this repository.**

## What is now composed

`MapGuestImagePs5(base, logical_size)` owns the complete transition:

1. round the Windows PE logical size to the 16 KiB native mapping granule;
2. reserve the exact guest address with `sceKernelReserveVirtualRange`;
3. allocate CPU direct memory;
4. replace the reservation at the same address using `sceKernelMapDirectMemory` with `PROT_READ|PROT_WRITE + MAP_FIXED`;
5. return one ownership object that is later released with unmap-before-physical-release ordering.

If direct backing fails cleanly, the still-owned virtual reservation is released. If a kernel call mutates its output address on failure or a wrong-address alias cannot be removed, ownership is considered ambiguous and the caller is told that the process must terminate instead of guessing cleanup.

## Device probe

`RunSyntheticGuestMemoryProbePs5()` is deliberately independent of Warcraft data.

Default test range:

- requested guest base: `0x140000000`;
- logical size: `0x5000`;
- rounded native mapping: `0x8000`;
- marker offset: `+0x2000`.

The probe:

1. creates the composed guest image mapping;
2. writes a fixed 64-bit marker into the direct-memory mapping;
3. reads the marker back;
4. tears down the mapping;
5. reports mapping/release statuses.

A passing log has the form:

```text
REFROZEN_PS5_GUEST_PROBE pass=1 base=140000000 logical=5000 mapped=8000 marker=5743335053354d41
```

This establishes only virtual-address reservation, CPU direct-memory mapping and teardown. It does **not** validate Vulkan, audio, input, Win32 APIs, Warcraft code or PE loading.

## Required action after the probe passes

Use the same composed mapping for the existing synthetic PE materializer, then execute the already-proven translated synthetic Win64 function. That will close the first full PS5 chain:

```text
exact VA -> direct memory -> PE materialization -> translated C/C++ -> guest data mutation -> teardown
```

Only after that synthetic chain is green on hardware should a private user-owned Warcraft module be introduced.
