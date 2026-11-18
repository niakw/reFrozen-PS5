#!/usr/bin/env python3
"""Embed a local binary as a C++ byte array for synthetic PS5 probes."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def emit_cpp(data: bytes, symbol: str) -> str:
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("invalid C/C++ symbol")
    rows = []
    for start in range(0, len(data), 16):
        chunk = data[start:start + 16]
        rows.append("  " + ", ".join(f"0x{value:02x}" for value in chunk) + ",")
    body = "\n".join(rows)
    return (
        "// Generated from a synthetic/public test binary. Do not edit.\n"
        "#include <cstddef>\n\n"
        f'extern "C" const unsigned char {symbol}[] = {{\n{body}\n}};\n'
        f'extern "C" const std::size_t {symbol}_size = sizeof({symbol});\n'
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--symbol", default="g_refrozen_synthetic_pe")
    args = parser.parse_args()
    data = args.input.read_bytes()
    if not data:
        parser.error("input must not be empty")
    try:
        text = emit_cpp(data, args.symbol)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
