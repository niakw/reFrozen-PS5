# Win64 runtime → PS5 compile census

Status: **compiler evidence only**. A translation unit compiling with the PS5 SDK is not proof of runtime correctness.

Pinned inputs:

- NightSightProductions/Recomp-Framework: `63742ed02e039b292bbf341a33b3bb8c73457fea`
- PS5 Payload SDK: v0.42, SHA-256 `8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da`

## Baseline

The unmodified Win64 candidate runtime produced:

- **6 PASS**
- **17 FAIL**

Direct PS5 compile passes:

```text
input.c
native.c
sockets.c
spvfix.c
teb.c
xreverb.c
```

## First portable adaptation

`scripts/ps5/patch_win64_runtime.py` replaces only Darwin's monotonic clock API in:

- `system.c`
- `window.c`

It converts `clock_gettime_nsec_np(CLOCK_UPTIME_RAW)` to a small
`clock_gettime(CLOCK_MONOTONIC)` helper. The patcher is fail-closed: each
pinned source fragment must occur exactly once.

After this adaptation:

- **8 PASS**
- **15 FAIL**

New passes:

```text
system.c
window.c
```

## Remaining first compiler blockers

| Unit | First observed blocker |
| --- | --- |
| bcrypt.c | CommonCrypto |
| boot.c | crt_externs.h |
| dinput.c | CoreGraphics |
| display.c | CoreGraphics |
| fiber.c | ARM64 context-switch assembly |
| files.c | copyfile.h |
| handles.c | pthread_main_np + libdispatch |
| kernel32.c | os_sync_wait_on_address |
| pdh.c | Mach |
| rt.c | Mach |
| steam.c | Mach-O/dyld + macOS Steam bridge |
| user32.c | CoreGraphics |
| vulkan.c | Mach-O/dyld / macOS Vulkan loader |
| wasapi.c | AudioToolbox |
| xaudio2.c | Mach clock first; CoreAudio path remains |
 
This list is ordered by **compiler evidence**, not perceived difficulty.

## Interpretation

The current Win64 candidate already gives us PS5-compilable source for guest
TLS/TEB, sockets, native replacements, input-side logic, SPIR-V fixes and
reverb. Generic system/message timing also needs only a small POSIX adaptation.

The next portable-core targets should be synchronization and file/process
helpers before UI, graphics and audio. Renderer/audio code should be replaced
with the existing PS5/Encore platform paths rather than emulating macOS APIs.
