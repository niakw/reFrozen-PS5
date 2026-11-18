#!/usr/bin/env python3
"""Generate exact Win64 guest -> native OpenGL thunks for a requested API set.

The ABI mapping follows the same proven strategy as NightSight Recomp-Framework
(MIT, tools/gen_gl.py), but this generator is deliberately allowlist-driven:
it emits only functions requested by the exact local game/import census.

Input headers must contain GLAPI ... APIENTRY/GLAPIENTRY glFoo(...) declarations.
No game binary or generated proprietary code is consumed here.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

PROTO_RE = re.compile(
    r"^[ \t]*GLAPI[ \t]+([^;\n]+?)[ \t]+"
    r"(?:APIENTRY|GLAPIENTRY)[ \t]+(gl\w+)[ \t]*"
    r"\(([^;]*?)\)[ \t]*;",
    re.M,
)
SPACE_RE = re.compile(r"\s+")

FLOAT_TYPES = {"GLfloat", "GLclampf"}
DOUBLE_TYPES = {"GLdouble", "GLclampd"}
INT32_TYPES = {
    "GLenum", "GLboolean", "GLbitfield", "GLbyte", "GLubyte",
    "GLshort", "GLushort", "GLint", "GLuint", "GLsizei", "GLfixed",
    "GLhalf", "GLclampx", "GLchar",
}
INT64_TYPES = {"GLint64", "GLuint64", "GLintptr", "GLsizeiptr"}
POINTER_LIKE_TYPES = {"GLsync"}
UNSAFE_CALLBACK_TYPES = {
    "GLDEBUGPROC", "GLDEBUGPROCARB", "GLVULKANPROCNV",
}


class GenerationError(ValueError):
    pass


@dataclass(frozen=True)
class Parameter:
    type: str
    name: str


@dataclass(frozen=True)
class Prototype:
    return_type: str
    name: str
    parameters: tuple[Parameter, ...]


def _norm(value: str) -> str:
    return SPACE_RE.sub(" ", value.strip())


def _base_type(value: str) -> str:
    value = _norm(value)
    value = re.sub(r"\b(const|volatile|restrict|__restrict|__restrict__)\b", "", value)
    value = SPACE_RE.sub(" ", value).strip()
    return value


def _split_params(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw == "void":
        return []
    # Function-pointer parameters require a callback bridge, not a raw host
    # cast. Fail closed instead of pretending a simple comma split is safe.
    if "(*" in raw or "APIENTRY *" in raw or "APIENTRYP" in raw:
        raise GenerationError("function-pointer parameter requires callback bridge")
    return [part.strip() for part in raw.split(",")]


def _parse_param(raw: str, index: int) -> Parameter:
    raw = _norm(raw)
    # Arrays in Khronos declarations are pointer parameters.
    raw = re.sub(r"\s*\[[^\]]*\]\s*$", " *", raw)
    match = re.match(r"(.+?)([A-Za-z_][A-Za-z0-9_]*)$", raw)
    if not match:
        raise GenerationError(f"cannot parse parameter {index}: {raw!r}")
    ty = _norm(match.group(1))
    name = match.group(2)
    if not ty:
        raise GenerationError(f"missing type for parameter {name}")
    return Parameter(ty, name)


def parse_headers(paths: list[Path]) -> dict[str, Prototype]:
    found: dict[str, Prototype] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for ret, name, raw_params in PROTO_RE.findall(text):
            if name in found:
                continue
            params = tuple(
                _parse_param(value, i)
                for i, value in enumerate(_split_params(raw_params))
            )
            found[name] = Prototype(_norm(ret), name, params)
    return found


def _arg_expr(param: Parameter, index: int) -> str:
    ty = _norm(param.type)
    base = _base_type(ty.replace("*", " "))
    if base in UNSAFE_CALLBACK_TYPES:
        raise GenerationError(
            f"{base}: callback/function-pointer argument needs a guest callback bridge"
        )
    if "*" in ty:
        slot = f"A{index}" if index < 4 else f"AN({index})"
        return f"({ty})(uintptr_t){slot}"
    if base in POINTER_LIKE_TYPES:
        slot = f"A{index}" if index < 4 else f"AN({index})"
        return f"({ty})(uintptr_t){slot}"
    if base in FLOAT_TYPES:
        return f"AF({index})" if index < 4 else f"rdf(c->rsp + 8 + 8 * {index})"
    if base in DOUBLE_TYPES:
        return f"AD({index})" if index < 4 else f"rdd(c->rsp + 8 + 8 * {index})"
    if base in INT32_TYPES or base in INT64_TYPES:
        slot = f"A{index}" if index < 4 else f"AN({index})"
        return f"({ty}){slot}"
    raise GenerationError(f"unsupported OpenGL argument type {ty!r}")


def _body(proto: Prototype) -> str:
    args = ", ".join(_arg_expr(param, i) for i, param in enumerate(proto.parameters))
    call = f"{proto.name}({args})"
    ret = _norm(proto.return_type)
    base = _base_type(ret.replace("*", " "))
    if ret in {"void", "GLvoid"}:
        return f"{call};"
    if "*" in ret or base in POINTER_LIKE_TYPES:
        return f"RET((uintptr_t){call});"
    if base in INT32_TYPES:
        return f"RET((uint32_t){call});"
    if base in INT64_TYPES:
        return f"RET((uint64_t){call});"
    if base in FLOAT_TYPES:
        return f"RETF({call});"
    if base in DOUBLE_TYPES:
        return f"RETD({call});"
    raise GenerationError(f"{proto.name}: unsupported OpenGL return type {ret!r}")


def generate(prototypes: dict[str, Prototype], requested: list[str]) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for name in requested:
        name = name.strip()
        if not name or name.startswith("#") or name in seen:
            continue
        if not re.fullmatch(r"gl[A-Za-z0-9_]+", name):
            raise GenerationError(f"invalid OpenGL function name {name!r}")
        if name not in prototypes:
            raise GenerationError(f"requested OpenGL function not found in headers: {name}")
        names.append(name)
        seen.add(name)

    lines = [
        "// Generated by scripts/ps5/gen_gl_guest_thunks.py - do not edit.",
        "// Win64 CPU-state ABI -> native PS5 OpenGL calls.",
        'extern "C" {',
        '#include "rt.h"',
        '}',
        "#include <GL/gl.h>",
        "#include <GL/glext.h>",
        "#include <cstdint>",
        "#include <cstring>",
        "",
        'extern "C" {',
    ]
    for name in names:
        proto = prototypes[name]
        try:
            body = _body(proto)
        except GenerationError as exc:
            raise GenerationError(f"{name}: {exc}") from exc
        lines.append(f"void I_opengl32_dll_{name}(CPU* c) {{ (void)c; {body} }}")
    lines += [
        "}",
        "",
        "namespace refrozen::ps5::graphics {",
        "namespace {",
        "struct GuestGlThunk { const char* name; gfn function; };",
        "constexpr GuestGlThunk kGuestGlThunks[] = {",
    ]
    for name in names:
        lines.append(f'    {{"{name}", I_opengl32_dll_{name}}},')
    lines += [
        "};",
        "}  // namespace",
        "",
        "std::uint64_t ResolveGeneratedGuestGlProc(const char* name) {",
        "  if (!name || !*name) return 0;",
        "  for (const auto& proc : kGuestGlThunks) {",
        "    if (std::strcmp(proc.name, name) == 0)",
        "      return rt_host_fn(proc.function, proc.name);",
        "  }",
        "  return 0;",
        "}",
        "",
        "}  // namespace refrozen::ps5::graphics",
        "",
    ]
    return "\n".join(lines)


def _read_allowlist(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header", type=Path, action="append", required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        prototypes = parse_headers(args.header)
        generated = generate(prototypes, _read_allowlist(args.allowlist))
    except (OSError, GenerationError) as exc:
        print(f"gl thunk generation failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generated, encoding="utf-8")
    print(f"generated {generated.count('void I_opengl32_dll_gl')} OpenGL guest thunks: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
