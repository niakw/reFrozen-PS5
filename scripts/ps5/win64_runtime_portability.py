#!/usr/bin/env python3
"""Static triage of a Win64 recomp runtime before a PS5 port.

The scanner reports host-platform dependencies only. It does not judge API
correctness and never records the absolute runtime path.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

PATTERNS = {
    "mach_api": re.compile(
        r"(?:#include\s*[<\"]mach/|\bmach_(?:vm|time|port|task)|\btask_self\b|"
        r"\bclock_gettime_nsec_np\b)"
    ),
    "apple_objc_ui": re.compile(
        r"(?:#import\s*[<\"](?:AppKit|Cocoa|Foundation|QuartzCore|Metal|"
        r"GameController|CoreHaptics)/|\bNS(?:Window|View|Application|Event)\b|"
        r"\bCAMetalLayer\b|\bMTL[A-Za-z0-9_]*\b)"
    ),
    "apple_media": re.compile(
        r"(?:#include\s*[<\"](?:AudioToolbox|CoreAudio|IOSurface)/|"
        r"\bAudioUnit\b|\bCoreAudio\b|\bIOSurface[A-Za-z0-9_]*\b)"
    ),
    "darwin_only_api": re.compile(
        r"(?:#include\s*[<\"](?:copyfile\.h|crt_externs\.h|malloc/malloc\.h)[>\"]|"
        r"\bcopyfile\s*\(|\bmalloc_size\s*\(|\b_NSGetEnviron\s*\(|"
        r"\bpthread_(?:threadid_np|setname_np)\s*\()"
    ),
    "arm64_context_asm": re.compile(
        r"(?:__asm__|asm)\s+volatile\s*\([^;]*(?:\bstp\s+x|\bldp\s+x|"
        r"\bmov\s+x\d+|\bsub\s+sp|\badd\s+sp|\bstp\s+d|\bldp\s+d)",
        re.DOTALL,
    ),
}

POSIX_HINT = re.compile(
    r"(?:\bpthread_[A-Za-z0-9_]+\b|\bmmap\s*\(|\bmunmap\s*\(|"
    r"#include\s*<sys/socket\.h>|\bsocket\s*\(|\bclock_gettime\s*\()"
)
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm"}


def audit_runtime(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("runtime root is not a directory")
    files = []
    totals = Counter()
    blocked_files = Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        categories: dict[str, int] = {}
        for name, pattern in PATTERNS.items():
            count = len(pattern.findall(text))
            if count:
                categories[name] = count
                totals[name] += count
                blocked_files[name] += 1
        posix_hints = len(POSIX_HINT.findall(text))
        files.append({
            "path": path.relative_to(root).as_posix(),
            "blockers": categories,
            "posix_hint_count": posix_hints,
            "portability_class": (
                "host_specific"
                if categories
                else "portable_candidate"
                if posix_hints or path.suffix.lower() in {".c", ".h"}
                else "needs_review"
            ),
        })
    return {
        "schema": 1,
        "root": None,
        "privacy_note": "absolute runtime source path intentionally omitted",
        "pattern_note": (
            "regex triage only; a blocker match means source adaptation is required "
            "or likely, not that the file cannot be ported"
        ),
        "summary": {
            "source_files": len(files),
            "host_specific_files": sum(
                1 for item in files if item["portability_class"] == "host_specific"
            ),
            "portable_candidate_files": sum(
                1 for item in files
                if item["portability_class"] == "portable_candidate"
            ),
            "blocker_matches": dict(sorted(totals.items())),
            "files_by_blocker": dict(sorted(blocked_files.items())),
        },
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_runtime(args.runtime)
    except (OSError, ValueError) as exc:
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
