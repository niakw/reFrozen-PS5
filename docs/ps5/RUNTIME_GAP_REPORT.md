# Architecture-aware runtime gap report

The local install census can now be compared against two different runtime
surfaces without mixing their ABI assumptions.

## PE32 / classic Win32

For 32-bit modules, `runtime_gap_report.py` compares imports against the
current reFrozen/x86recomp HLE surface. This is the path relevant to the
existing 1.26a work and potentially other 32-bit Classic builds after their
symbols/functions are recovered.

## PE32+ / classic Win64

For 64-bit modules, pass a local Win64 recomp runtime source tree:

```sh
python3 scripts/ps5/runtime_gap_report.py private/install-census.json \
  --win64-runtime-root /path/to/Recomp-Framework/runtime \
  --output private/runtime-gaps.json
```

The report records only handler counts/statuses; it deliberately does not
record the absolute runtime path.

A matching handler is marked `reference_win64_hle`. An API implemented only
in the other architecture runtime is `reference_other_arch`: it is useful
source material, but **not** coverage for the selected ABI. APIs with no
candidate implementation remain `unmapped`.

Every entry keeps `ps5_status=unverified` until that path is compiled and
exercised on PS5.

This lets a private scan of an exact Warcraft III installation answer, before
we port anything:

- which modules are 32-bit vs 64-bit;
- which local DLLs satisfy imports themselves;
- which OS APIs already have a candidate implementation for the correct ABI;
- which handlers exist only in the other runtime and need adaptation;
- which APIs have no implementation at all.

No game file or generated game code needs to leave the local/private build
environment.
