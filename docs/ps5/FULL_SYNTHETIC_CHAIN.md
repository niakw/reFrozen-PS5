# Full synthetic recompilation chain before hardware qualification

Status: host CI experiment. No Blizzard data.

This gate connects every memory/recompilation component that can be validated without a PS5:

```text
synthetic Win64 PE
      |
      v
pinned Win64 static lifter -> generated C
      |
      v
production PS5 wrapper API
      |
      +-> exact guest VA reservation
      +-> direct-memory backing
      |
      v
PE header/section materialization at 0x140000000
      |
      v
translated function at guest 0x140001000
      |
      +-> RIP-relative load/store at guest 0x140002000
      |
      v
.data: 41 -> 42
      |
      v
unmap -> physical release -> VA confirmed free
```

On Linux, only the kernel calls are replaced by narrow test shims. The production functions
`ReserveExactGuestImagePs5`, `MapDirectGuestBackingPs5`,
`MapGuestImagePs5` and `ReleaseGuestImagePs5` are linked unchanged.

The fake kernel shim uses safe host primitives:

- reservation: `MAP_FIXED_NOREPLACE + PROT_NONE`;
- backing replacement: `MAP_FIXED + PROT_READ|PROT_WRITE`;
- no host execute permission for PE bytes;
- teardown: real `munmap`, then fake direct-memory release.

## Pass meaning

A green gate proves, on x86-64 host:

- Win64 translation still preserves the preferred guest data address;
- logical `0x5000` image size becomes `0x8000` native backing;
- the full synthetic PE is copied at its preferred Windows address;
- translated code reads/writes the materialized image correctly;
- wrapper ownership transitions and teardown work as designed.

It does **not** prove the PS5 firmware accepts those addresses or syscalls.

## Next hardware gate

Run the already-compiled `RunSyntheticGuestMemoryProbePs5()` against the real PS5 kernel.
If it passes, replace the marker-only body with the same synthetic PE materialization and translated function invocation used by this host gate.

No user-owned Warcraft module should be introduced before that synthetic device chain is green.
