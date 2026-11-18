# PS5 direct-memory backing for identity-mapped PE images

Status: host-tested ownership state machine + compile-only native adapter. **No direct-memory Warcraft image has been mapped on PS5 yet.**

## Logical PE size vs PS5 mapping size

Windows PE `SizeOfImage` is commonly aligned to 4 KiB. Encore's native PS5 work uses a 16 KiB kernel mapping granule.

The runtime therefore keeps two sizes:

- **logical size**: exact PE `SizeOfImage`, used by the loader and address checks;
- **mapped size**: logical size rounded up to 16 KiB for PS5 reservation/direct memory.

Example: logical `0x5000` -> mapped `0x8000`.

The rounded tail is backing only. It is not part of the guest PE image.

## Native sequence

The current design is deliberately two-phase:

1. `ReserveExactGuestImagePs5` rounds the logical PE image size to the PS5 granule and proves that the requested guest VA can be reserved exactly.
2. `MapDirectGuestBackingPs5` allocates direct memory type 12 and maps it over that reservation with:
   - `PROT_READ | PROT_WRITE`
   - `MAP_FIXED`
   - 16 KiB alignment
   - **no `PROT_EXEC`**
3. The PE materializer copies headers/sections into the logical image portion and zero-fills virtual tails.
4. Later protection planning may reduce host pages to read-only where 16 KiB granularity permits.
5. Teardown unmaps the VA first; physical memory is released only after a successful unmap.

## Ownership rules

The backing state machine follows the fail-closed rules already used by Encore:

- allocation failure owns no new mapping;
- map failure with an unchanged output VA may safely release the allocated physical block;
- a failing map call that **mutates** its output VA has ambiguous alias ownership: do not guess how to clean it up; the runtime should fail hard;
- a successful map returned at the wrong VA is explicitly unmapped before the physical block is released;
- if unmap fails during teardown, do **not** release the physical block while an alias may still exist.

These rules prefer a bounded leak/process abort over use-after-free or a stale physical alias.

## Current evidence

Host tests cover:

- 4 KiB logical image -> 16 KiB rounding;
- exact mapping success;
- direct-memory extent unavailable;
- allocation failure;
- mapping failure and physical rollback;
- mutated output on failed mapping;
- successful mapping at the wrong VA and cleanup;
- cleanup/unmap/release failures;
- GPU collision-policy rejection;
- teardown ordering.

The native adapter binds the state machine to:

- `sceKernelGetDirectMemorySize`
- `sceKernelAllocateDirectMemory`
- `sceKernelMapDirectMemory`
- `sceKernelReleaseDirectMemory`
- `munmap`

## Next device gate

A real PS5 probe must reserve a **synthetic** range such as `0x140000000`, map a small rounded direct-memory block there, write/read a marker, unmap it, and release the physical backing. Only after that passes should the PE materializer be run against PS5 direct memory.
