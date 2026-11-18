# Synthetic Win64 WGL import chain

Status: **PS5 ABI link proof; real hardware execution and real EGL/OpenGL remain open.**

This gate exercises the graphics-facing Win64 import boundary without any
Warcraft III binary or asset.

## Guest sequence

The public PE32+ fixture executes:

```text
opengl32!wglCreateContext(0x1111)
opengl32!wglMakeCurrent(0x1111, returned_context)
opengl32!wglGetProcAddress("glGetString")
opengl32!wglSwapBuffers(0x1111)
```

The guest stores the returned WGL handle, GL proc token and swap result in its
mapped `.data` section.

## Path covered

```text
synthetic Win64 PE
  -> pinned Win64 static translator
  -> generated IAT calls
  -> reFrozen PS5 wgl_guest_runtime_ps5.cpp
  -> WglRegistry
  -> deterministic backend contract
  -> PS5 Payload SDK ELF
```

The ELF also uses the production exact-address/direct-memory guest mapping and
PE materializer. The deterministic backend validates context creation,
make-current, swap and cleanup arguments without requiring a graphics driver.

## CI evidence

Workflow: `PS5 synthetic Win64 WGL import chain`.

Validated on 18 November 2026:

- one Win64 function recovered from `.pdata`;
- four WGL imports referenced;
- translator report: `UNSUPPORTED: {}`;
- the generated functions and real WGL shim symbols link into an x86-64 PS5 PIE;
- no desktop ELF interpreter or Warcraft/Blizzard payload string is present;
- PS5 ELF SHA-256 from run 44232908504:
  `c5c14578fff15e8237f7a65681f1568222bd65e8213259ee6bf10b00c660f006`.

Normal unresolved symbols are PS5 runtime imports (libc/pthread and
`sceKernel*` memory primitives). No extra emulated-TLS helper was introduced
by the WGL registry in this link proof.

## What this proves

It proves that the translated Win64 calling convention can reach the project's
WGL compatibility layer and that the resulting C/C++ code links for the PS5
ABI.

It does **not** prove:

- execution of this ELF on a PS5;
- creation of an EGL/OpenGL context;
- compatibility with the pinned Encore `ps5-opengl` implementation;
- any Warcraft III renderer/import set;
- presentation of a frame.

## Next graphics gate

Replace only the deterministic backend with `EglWglBackend` built against the
same audited PS5 OpenGL stack used by Encore. The first real-device graphics
probe should:

1. open the PS5 EGL display;
2. create a compatibility-profile GL context;
3. make it current through the WGL registry;
4. resolve one GL function;
5. clear/present a deterministic frame;
6. swap and destroy cleanly.

Only after that gate should a private Warcraft Classic executable be connected
to the OpenGL route.
