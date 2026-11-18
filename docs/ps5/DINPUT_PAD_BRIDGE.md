# PS5 DirectInput pad bridge

Status: host-test + PS5 Win32 object-link gate; hardware behavior is not yet qualified.

The native PS5 bridge consumes four small DirectInput-style event entry points:

- `di_key(scan, extended, down)`
- `di_mouse_move(dx, dy)`
- `di_mouse_wheel(delta)`
- `di_mouse_button(button, down)`

For the Win64 research runtime these hooks already existed. The Warcraft III
1.26a **Win32 x86recomp runtime now exposes the same four C hooks from its
existing `RawInput` implementation**. They call `EmitRawInput()`, so mouse
and keyboard state flows through SwARc's normal `dinput8.dll` HLE without
reimplementing IDirectInput.

This deliberately does **not** synthesize Win32 window messages or user32 key
state. Those remain owned by the host window/event layer. Therefore this bridge
qualifies the DirectInput device path only; menus or code that depend on
`WM_KEYDOWN`, `WM_MOUSEMOVE` or `GetKeyState` still need the separate
native user32/window adapter.

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

The host test validates open/poll/edge/release/intercept behavior. The PS5 SDK
object gate cross-compiles the real bridge with `x86_64-sie-ps5`, then
relocatably links it with the 55-object Win32 runtime closure. The gate requires
`di_key`, `di_mouse_move`, `di_mouse_wheel` and `di_mouse_button` to be
resolved by the patched Win32 runtime while native `scePad` and UserService
imports remain for the final PS5 title linker.

Neither test proves `scePadReadState` behavior on the user's console.
