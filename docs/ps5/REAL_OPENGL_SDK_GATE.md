# Real PS5 OpenGL SDK gate

Status: **consumer link + registered-title package gate moved to preserved OpenGL SDK 1.0.2; hardware execution remains separate.**

## Why this gate exists

Host EGL headers proved only that the reFrozen WGL backend was syntactically
portable. Warcraft Classic needs a stronger boundary: the backend must compile
and link against the exact PS5 OpenGL SDK family already qualified by Encore.

The source is taken from the pinned Encore vendor snapshot:

- vendor repository: `niakw/Prospero.Eden-Encore-vendor`;
- vendor commit used by CI: `1e51d1f3383f149a599e36052aba7d887d4b1f77`;
- `sources/opengl-source/VENDOR-ORIGIN.json` records upstream commit
  `ad2807d41cef2681882a9ee0d20808779f74b7cd`;
- Payload SDK: public v0.42, checksum already used by the reFrozen PS5 gates.

CI copies that source out of the checkout, fetches only its pinned transitive
dependencies, builds the installed OpenGL 4.6 SDK, verifies
`manifest.sha256`, and then consumes the canonical
`share/ps5-opengl/ps5-opengl.mk` interface.

No private Sony SDK or Warcraft file is used.

## Compatibility-profile evidence already present upstream

The vendored PS5 OpenGL engineering record contains a hardware gate for
OpenGL 4.6 Compatibility at source commit `0f127f0`. The retained report
states that the test passed:

- GLSL 4.60 compatibility contexts;
- material ambient state;
- all eight alpha-test functions;
- color clamping;
- point sprites;
- polygon mode/culling restoration;
- legacy `GL_QUADS`, `GL_QUAD_STRIP`, and `GL_POLYGON` draws;
- provoking-vertex behavior;
- context sharing/migration and cleanup.

The report records `legacy=8/8 share=1 result=0` and eboot SHA-256
`63ffcaaa8ef71fd5e77a9d0f9141dad18d348e40e1c89a210a78fba0514a1254`.

This is strong evidence that a Warcraft-era legacy OpenGL path is feasible on
the selected graphics stack. It is not evidence that Warcraft III itself has
been run.

## reFrozen consumer probe

`tests/ps5/ps5_wgl_egl_real_sdk_probe.cpp` instantiates the production
`EglWglBackend` and `WglRegistry`, then requests exactly the compatibility
profile intended for Warcraft Classic:

1. create a compatibility context;
2. make it current on the fullscreen device-context token;
3. resolve `glGetString`;
4. swap buffers;
5. clear current;
6. destroy the context.

The CI only compiles and links this sequence. The success string embedded in
the ELF is **not** a hardware receipt.

## Acceptance

The link gate is accepted only when:

- the vendored origin commit matches the pinned identity;
- the installed SDK manifest verifies byte-for-byte;
- reFrozen compiles with the installed public EGL/GL headers;
- the consumer links through the SDK's canonical static dependency graph;
- the ELF is x86-64 and contains the real EGL entry points;
- no host runner path or Warcraft/Blizzard content is embedded.

## Hardware gate after link

A registered-title probe (not elfldr) must execute the same sequence and
present a deterministic frame. That probe should use the OpenGL package's
application heap/wrap contract and preserve its own exact build receipt.

Only after that passes should a privately supplied Warcraft Classic executable
be connected to the real WGL/EGL path.
