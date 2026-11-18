#!/usr/bin/env python3
"""Validate the terminal receipt emitted by the registered WGL PS5 probe.

This parser never contacts the console. Give it the copied /download0/ps5-opengl.log
and, optionally, the exact eboot.bin that was installed or its expected SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SUCCESS_RE = re.compile(
    r"^REFROZEN_PS5_WGL_TITLE pass=1 "
    r"version=(?P<version>.+?) renderer=(?P<renderer>.+?) "
    r"width=(?P<width>\d+) height=(?P<height>\d+) "
    r"frames=(?P<frames>\d+) clear=(?P<clear>[01]) delete=(?P<delete>[01])$"
)
TERMINAL_PREFIX = "REFROZEN_PS5_WGL_TITLE "


class ReceiptError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_terminal_receipt(text: str) -> dict:
    receipts = [line.strip() for line in text.splitlines() if line.strip().startswith(TERMINAL_PREFIX)]
    if not receipts:
        raise ReceiptError("no REFROZEN_PS5_WGL_TITLE receipt found")
    line = receipts[-1]
    match = SUCCESS_RE.fullmatch(line)
    if not match:
        if "pass=0" in line:
            raise ReceiptError(f"terminal hardware receipt reports failure: {line}")
        raise ReceiptError(f"malformed terminal hardware receipt: {line}")
    data = match.groupdict()
    width = int(data["width"])
    height = int(data["height"])
    frames = int(data["frames"])
    clear = int(data["clear"])
    delete = int(data["delete"])
    if width <= 0 or height <= 0:
        raise ReceiptError("invalid surface dimensions")
    if frames != 120:
        raise ReceiptError(f"expected exactly 120 presented frames, got {frames}")
    if clear != 1 or delete != 1:
        raise ReceiptError("context teardown did not complete")
    version = data["version"].strip()
    renderer = data["renderer"].strip()
    if not version or not renderer:
        raise ReceiptError("missing GL_VERSION or GL_RENDERER")
    return {
        "schema": 1,
        "passed": True,
        "version": version,
        "renderer": renderer,
        "width": width,
        "height": height,
        "frames": frames,
        "clear": bool(clear),
        "delete": bool(delete),
        "receipt_count": len(receipts),
        "terminal_line": line,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--eboot", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = parse_terminal_receipt(args.log.read_text(encoding="utf-8", errors="replace"))
        if args.eboot:
            digest = sha256_file(args.eboot)
            report["eboot_sha256"] = digest
            if args.expected_sha256 and digest.lower() != args.expected_sha256.lower():
                raise ReceiptError(
                    f"eboot SHA-256 mismatch: {digest} != {args.expected_sha256.lower()}"
                )
        elif args.expected_sha256:
            raise ReceiptError("--expected-sha256 requires --eboot")
    except (OSError, ReceiptError) as exc:
        parser.error(str(exc))

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
