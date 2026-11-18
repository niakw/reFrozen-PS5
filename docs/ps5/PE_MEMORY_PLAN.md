# Translated PE image memory/protection plan on PS5

Status: static planning and synthetic tests. No Warcraft image or PS5 device mapping is performed here.

## Core decision: guest `.text` is not host executable

The Win64 recompiler translates guest machine code into native C/C++ functions. Runtime dispatch calls those native functions. The identity-mapped PE image is retained because the game expects its data, PE headers, IAT, RTTI, vtables, strings and absolute/RIP-relative addresses to exist at Windows virtual addresses.

Therefore the copied guest PE pages do **not** need `PROT_EXEC` on PS5. Host W^X can stay intact even when a Windows section has `IMAGE_SCN_MEM_EXECUTE`.

## 4 KiB Windows sections vs 16 KiB PS5 granules

PE sections commonly begin on 4 KiB boundaries. Encore's native memory work uses a 16 KiB PS5 kernel granule. Multiple Windows sections can therefore share one host granule.

Example from the public synthetic fixture:

- headers: `0x140000000`
- `.text`: `+0x1000` (guest RX)
- `.data`: `+0x2000` (guest RW)
- `.pdata`: `+0x3000` (guest R)

All four occupy one 16 KiB host granule. The host page must be RW because `.data` is writable, but it remains **non-executable**. The planner records that write permission is broader than Windows semantics.

Exact Windows page protection may later require a 4 KiB guest-protection table checked by translated memory helpers, similar in principle to Encore's per-guest-page access metadata. It should not be implemented until real Warcraft access patterns show it is needed.

## Tooling

`pe_probe.py` now records:

- section RVA and virtual/raw sizes,
- raw file offset,
- PE characteristics,
- guest read/write/execute flags,
- `SizeOfHeaders`.

Generate a private install census, then:

```sh
python3 scripts/ps5/pe_protection_plan.py \
  build/private-war3-census.json \
  --output build/private-war3-protection-plan.json
```

The plan coalesces 16 KiB host segments, never requests host execute permission, and identifies granules whose host write permission is broader than one or more guest sections.

## Loader order proposed

1. Validate exact PE base/range and collision policy.
2. Reserve the complete image range exactly.
3. Allocate/map backing memory without host execute permission.
4. Copy PE headers and section raw bytes; zero virtual tails.
5. Bind/rewrite the IAT to synthetic host-function addresses or translated guest DLL exports.
6. Apply coarse host R/RW protection by 16 KiB segment where supported.
7. Initialize TLS/loader structures.
8. Enter the translated native entry point.

This order is not yet device-qualified.
