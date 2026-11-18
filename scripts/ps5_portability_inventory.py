#!/usr/bin/env python3
"""Inventory host-specific integration points before attempting a PS5 port.

Static, read-only and safe on GitHub Actions: never needs game assets.
The report is evidence for triage, not a claim of PS5 compatibility.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

PATTERNS = {
    "apple_platform": r"(__APPLE__|__MACH__|APPLE|macOS|MacOS|/Library/Application Support|\.dylib\b|\.app\b|Info\.plist|codesign|xcrun)",
    "arm64_assumptions": r"(__aarch64__|__arm64__|arm64|aarch64|NEON)",
    "unix_dynamic_loading": r"\b(dlopen|dlsym|dlerror|RTLD_NOW|RTLD_LOCAL)\b",
    "unix_system_calls": r"\b(mmap|munmap|mprotect|pthread_|sigaction|clock_gettime|mach_)\b",
    "graphics": r"\b(OpenGL|opengl|GL_[A-Z_0-9]+|Vulkan|SDL_GL_|Direct3D)\b",
    "audio": r"\b(DirectSound|SDL_Audio|waveOut|Miles)\b",
    "network": r"\b(wsock32|WSA[A-Za-z0-9_]+|socket\(|sendto\(|recvfrom\()",
    "build_host_paths": r"(/opt/homebrew|/usr/local/opt|CMAKE_OSX|Darwin|MACOSX)",
}
SUFFIXES = {".cpp", ".c", ".h", ".hpp", ".cmake", ".sh", ".py", ".txt"}
NAMES = {"CMakeLists.txt"}
SCAN_DIRS = ("src", "scripts", "config", "patches", "tests")

def inventory(root: Path) -> dict:
    findings = []
    counts = {name: 0 for name in PATTERNS}
    compiled = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in PATTERNS.items()}
    for directory in SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for file in sorted(base.rglob("*")):
            if not file.is_file() or (file.suffix not in SUFFIXES and file.name not in NAMES):
                continue
            if file.is_symlink() or file.stat().st_size > 2_000_000:
                continue
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except (UnicodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                matched = [name for name, rx in compiled.items() if rx.search(line)]
                if matched:
                    for name in matched:
                        counts[name] += 1
                    findings.append({"path": file.relative_to(root).as_posix(), "line": i, "categories": matched})
    cmake = root / "CMakeLists.txt"
    if cmake.is_file():
        for i, line in enumerate(cmake.read_text(encoding="utf-8").splitlines(), 1):
            matched = [name for name, rx in compiled.items() if rx.search(line)]
            if matched:
                for name in matched:
                    counts[name] += 1
                findings.append({"path": "CMakeLists.txt", "line": i, "categories": matched})
    return {"schema": 1, "scope": list(SCAN_DIRS) + ["CMakeLists.txt"], "counts": counts,
            "findings": findings, "disclaimer": "Regex hints only; no guest game binaries, compiled runtime, or PS5 execution validated."}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inventory(args.root.resolve())
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")

if __name__ == "__main__":
    main()
