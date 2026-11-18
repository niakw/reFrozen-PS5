# PS5 exact guest virtual-address reservation

Status: host contract + compile-only adapter. **No real PS5 reservation has been executed by this repository yet.**

## Why exact addresses matter for Win64 recompilation

The experimental Win64 lifter uses identity-mapped guest pointers: typical PE images are loaded at preferred addresses such as `0x140000000`, and translated DLLs may live around `0x180000000`. A PS5 port therefore cannot silently accept a kernel-selected replacement address without either relocating every guest pointer/reference or changing the generated runtime model.

For the first implementation, reFrozen PS5 chooses the conservative contract:

> reserve the requested guest range exactly, or fail.

## Encore evidence reused

Current Encore PS5 code already calls:

- `sceKernelReserveVirtualRange`
- `sceKernelAllocateDirectMemory`
- `sceKernelMapDirectMemory`
- `sceKernelReleaseDirectMemory`
- `munmap`

Encore also documents a RADV-owned interval at `[0x200000000, 0x300000000)` and device-memory mappings beginning at `0x4000000000`. This fork treats those values as a **current collision policy**, not immutable PS5 hardware facts.

The common Win64 bases used by our synthetic tests — `0x140000000` and `0x180000000` — are below that RADV interval. This does **not** prove those ranges are free on a real process.

## Contract

`ReserveExactGuestRange`:

1. validates size/alignment/overflow,
2. rejects known Encore GPU collision regions,
3. calls the supplied reservation API with the exact requested address,
4. accepts success only if the returned pointer is identical,
5. releases a successful reservation returned at the wrong address,
6. treats a **failed** reservation that mutates its output pointer as ambiguous ownership and does not guess how to release it.

The PS5 adapter binds that contract to `sceKernelReserveVirtualRange` and `munmap`.

## What remains before a Win64 image can load

- Run the object smoke against a real `PS5_PAYLOAD_SDK`.
- On-device probe of exact reservations at synthetic candidate addresses.
- Determine whether a successful VA reservation can be backed section-by-section with direct memory while preserving PE protections.
- Test release/unmap ownership.
- Load a **synthetic** PE image and exercise a translated function reading/writing identity-mapped data.
- Only after those gates, attempt user-owned Warcraft binaries.

Do not use `MAP_FIXED`/direct-memory mapping over an unverified address. A collision with the frontend, loader, RADV or another library would be process-corrupting.
