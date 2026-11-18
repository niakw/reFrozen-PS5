#!/usr/bin/env python3
"""Close the private Warcraft OpenGL surface from static + dynamic evidence.

Inputs:
- local PE census from scan_install.py / pe_probe.py;
- optional observed wglGetProcAddress names (one per line);
- the exact PS5/Mesa GL headers.

Outputs contain only API names, provenance metadata and generated shim source.
No game bytes or absolute paths are copied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from scripts.ps5.gl_allowlist_from_census import (
    CensusError,
    derive_static_gl_surface,
)
from scripts.ps5.gen_gl_guest_thunks import (
    GenerationError,
    generate,
    parse_headers,
)

GL_NAME_RE = re.compile(r"^gl[A-Za-z0-9_]+$")
WGL_NAME_RE = re.compile(r"^wgl[A-Za-z0-9_]+$")


class SurfaceClosureError(ValueError):
    pass


def read_observed(path: Path | None) -> dict[str, list[str]]:
    gl: set[str] = set()
    wgl: set[str] = set()
    rejected: set[str] = set()
    if path is None:
        return {"gl": [], "wgl": [], "rejected": []}
    for raw in path.read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        if GL_NAME_RE.fullmatch(name):
            gl.add(name)
        elif WGL_NAME_RE.fullmatch(name):
            wgl.add(name)
        else:
            rejected.add(name)
    return {
        "gl": sorted(gl),
        "wgl": sorted(wgl),
        "rejected": sorted(rejected),
    }


def close_surface(census: dict, observed: dict[str, list[str]]) -> dict:
    static = derive_static_gl_surface(census)
    if observed["rejected"]:
        raise SurfaceClosureError(
            "unexpected dynamic proc names: " + ", ".join(observed["rejected"])
        )
    static_gl = set(static["static_gl_functions"])
    dynamic_gl = set(observed["gl"])
    union = sorted(static_gl | dynamic_gl)
    return {
        "schema": 1,
        "static_gl_functions": sorted(static_gl),
        "dynamic_gl_functions": sorted(dynamic_gl),
        "dynamic_wgl_functions": observed["wgl"],
        "all_gl_functions": union,
        "counts": {
            "static_gl": len(static_gl),
            "dynamic_gl": len(dynamic_gl),
            "dynamic_wgl": len(observed["wgl"]),
            "all_gl": len(union),
        },
        "static_provenance": static["provenance"],
        "static_ordinal_imports": static["ordinal_imports"],
        "note": (
            "all_gl_functions is the exact observed/imported GL thunk surface "
            "for this census+trace set; further runtime coverage can add names."
        ),
    }


def render_allowlist(names: list[str]) -> str:
    return (
        "# Generated from static PE imports plus observed wglGetProcAddress names.\n"
        "# Safe metadata only; no game code/assets.\n"
        + "\n".join(names)
        + ("\n" if names else "")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--header", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        census = json.loads(args.census.read_text(encoding="utf-8"))
        observed = read_observed(args.observed)
        report = close_surface(census, observed)
        prototypes = parse_headers(args.header)
        generated = generate(prototypes, report["all_gl_functions"])
    except (
        OSError,
        json.JSONDecodeError,
        CensusError,
        GenerationError,
        SurfaceClosureError,
    ) as exc:
        print(f"GL surface closure failed: {exc}", file=sys.stderr)
        return 1

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "gl-allowlist.txt").write_text(
        render_allowlist(report["all_gl_functions"]), encoding="utf-8"
    )
    (out / "gl-surface.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "gl-guest-thunks.cpp").write_text(generated, encoding="utf-8")
    print(
        "GL surface closed from current evidence: "
        f"static={report['counts']['static_gl']} "
        f"dynamic={report['counts']['dynamic_gl']} "
        f"union={report['counts']['all_gl']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
