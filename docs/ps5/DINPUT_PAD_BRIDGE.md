# PS5 DirectInput pad bridge

Status: compiler/host-test gate. Hardware behavior is not yet qualified.

The Win64 runtime already exposes the original DirectInput event entry points:

- `di_key(scan, extended, down)`
- `di_mouse_move(dx, dy)`
- `di_mouse_wheel(delta)`
- `di_mouse_button(button, down)`

The PS5 bridge feeds these entry points from a native DualSense sample without changing the guest-facing DirectInput implementation.

## Initial RTS mapping

| DualSense | Warcraft/DirectInput action |
| --- | --- |
| Right stick | Relative mouse pointer |
| Cross | Left mouse button |
| Circle | Right mouse button |
| Options | Escape |
| D-pad | Extended arrow keys |
| L1 | Mouse wheel +120 |
| R1 | Mouse wheel -120 |

Digital events are edge-triggered. Wheel inputs trigger only on a rising edge so a held shoulder is not repeated at the pad poll frequency. Right-stick movement has a 12% deadzone and fractional accumulation.

The mapping is deliberately small. It does not replace physical keyboard/mouse support and should become user-configurable only after the first hardware gameplay evidence.

## ABI

`ps5_pad_contract.hpp` is a minimal independently-authored interoperability declaration matching the 120-byte native pad sample already used by Encore. No proprietary SDK header is copied.

## Qualification

The host test validates open/poll/edge/release/intercept behavior. The PS5 SDK object gate cross-compiles the real bridge with `x86_64-sie-ps5`. Neither test proves `scePadReadState` behavior on the user's console.
