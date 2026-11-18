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


## Current PS5 portability census — 2026-11-18

After the merged portable-core work plus the PS5 display/user32 adaptation in this branch, the pinned Win64 runtime compiles **17 / 23** C translation units with Payload SDK v0.42.

Passing units:

```text
boot.c
display.c
fiber.c
files.c
handles.c
input.c
kernel32.c
native.c
pdh.c
rt.c
sockets.c
spvfix.c
system.c
teb.c
user32.c
window.c
xreverb.c
```

Remaining compiler blockers:

| Unit | Platform dependency / disposition |
| --- | --- |
| `bcrypt.c` | CommonCrypto; replace only when exact Warcraft crypto imports are known or add a small platform-neutral crypto backend. |
| `dinput.c` | CoreGraphics/AppKit mouse capture; high priority for keyboard/mouse gameplay. |
| `steam.c` | Mach-O/dyld + Steam-for-Mac bridge; not on the first offline/LAN Warcraft path. |
| `vulkan.c` | macOS Vulkan loader; not on the selected Warcraft `-graphicsapi OpenGL` path. |
| `wasapi.c` | AudioToolbox/CoreAudio; replace with the PS5 audio backend. |
| `xaudio2.c` | CoreAudio/Mach timing; replace with the PS5 audio backend if the target binary imports it. |

CI evidence: runtime census run `44268238481` reports `passed=17 failed=6` and explicitly requires `display.c` and `user32.c` to PASS.

This is compiler coverage, not runtime/device qualification. The display implementation exposes optional weak PS5 hooks so real scanout state can be connected after the registered WGL/EGL graphics probe is qualified.


## DirectInput portability increment

The DirectInput unit now compiles for the PS5 ABI after replacing only its host-facing macOS pieces:

- CoreGraphics/AppKit capture calls are removed;
- monotonic event timestamps use POSIX `CLOCK_MONOTONIC`;
- exclusive mouse capture is delegated through optional weak hook `rt_ps5_mouse_capture(int)`;
- keyboard/mouse state, buffered DirectInput events and COM vtables remain unchanged.

CI runtime census run `44268611168` reports **18 PASS / 5 FAIL**, with `dinput.c PASS`.

Remaining failures are now limited to:

```text
bcrypt.c
steam.c
vulkan.c
wasapi.c
xaudio2.c
```

For the selected Warcraft Classic OpenGL path, `steam.c` and `vulkan.c` are not first-launch requirements. Audio is the next platform runtime priority; `bcrypt.c` should be driven by the exact private import census rather than implemented speculatively.


## Native XAudio2 output increment

The Win64 XAudio2 engine now compiles for the PS5 ABI with its guest-facing logic unchanged. Only the macOS host output was replaced:

- CoreAudio / Mach dependencies removed from `xaudio2.c`;
- the existing XAudio2 voice graph, source/submix/master mixing, callbacks, effects and 10 ms render pass remain intact;
- stereo float output feeds `ps5_audio_out_bridge.c`, which converts to S16 and submits blocking 256-frame grains through `sceAudioOut`;
- silent fallback uses `CLOCK_MONOTONIC`;
- the bridge itself is compiled with Payload SDK v0.42 under `-Wall -Wextra -Werror`;
- a host test verifies float→S16 conversion, exact 256-frame buffering, final zero padding, drain and close semantics.

Compiler evidence: runtime census run `44270441940` reports **19 PASS / 4 FAIL**, including `xaudio2.c PASS`.

Remaining compiler-red units:

```text
bcrypt.c
steam.c
vulkan.c
wasapi.c
```

For the selected OpenGL Warcraft path, Steam and the macOS Vulkan runtime remain outside the first-launch route. WASAPI can reuse the same native AudioOut bridge if the exact Warcraft binary imports it. `bcrypt.c` remains import-driven rather than speculative.
