# Synthetic Win64 IAT/import gate

Status: **compile/link proof until executed on PS5 hardware**.

This gate validates the next generic mechanism needed by a real Windows game:
translated code crossing from a guest Win64 `call [IAT]` into a native host
handler.

## Public guest fixture

`scripts/ps5/synthetic_pe64_import.py` builds a deterministic PE32+ image with:

- preferred base `0x140000000`;
- one import: `KERNEL32.dll!GetTickCount64`;
- a real `.idata` import descriptor, ILT and IAT;
- an entry function that creates Win64 shadow space, calls the IAT slot,
  stores RAX in `.data`, restores RSP and returns;
- `.pdata` / `.xdata` sufficient for function discovery.

The fixture contains no Blizzard data.

## Translation boundary

The pinned Win64 translator recognizes the RIP-relative IAT call and emits:

```text
I_kernel32_dll_GetTickCount64(CPU*)
```

Generated `tables.c` also contains a weak fail-closed import stub. The PS5
probe links a **strong** native handler from
`tests/ps5/ps5_win64_import_handlers.c`, returning
`0x123456789abcdef0`.

The final ELF inspection requires the strong handler to be a `T` symbol and
keeps an observable fallback counter for `unimpl_import`.

## Hardware semantics

The synthetic PE logical image is `0x6000` bytes. PS5 backing is rounded to
the native mapping granularity, leaving mapped space above the logical image.
For this test only, the top of that backing is used as a tiny guest stack so
the translated IAT call can push a return address and use its Win64 shadow
space.

Expected device result:

```text
REFROZEN_PS5_IMPORT_CHAIN pass=1 ... value=123456789abcdef0 calls=1 fallback=0
```

This demonstrates:

1. PE import parsing;
2. IAT recognition by the static translator;
3. generated guest-to-native call boundary;
4. native PS5 handler override;
5. real guest stack writes;
6. return-value propagation back into translated Win64 code.

It does **not** prove the full Win32/Win64 API surface required by Warcraft III.
The private install census will decide which handlers to port next.
