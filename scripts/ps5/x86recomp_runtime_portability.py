#!/usr/bin/env python3
"""Static portability census for the patched x86recomp Win32 runtime.

This script never reads Warcraft files. It inspects only runtime source text and
classifies obvious host/platform dependencies before PS5 compiler work.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

SUFFIXES={".c",".cc",".cpp",".h",".hpp",".m",".mm"}
PATTERNS={
    "apple_framework": re.compile(r"\b(CoreFoundation|CoreGraphics|CoreAudio|AudioToolbox|AppKit|Cocoa|QuartzCore|IOKit|GameController)\b|#\s*include\s*[<\"](?:mach|dispatch|objc)/",re.I),
    "darwin_api": re.compile(r"\b(mach_|mach_absolute_time|pthread_main_np|clock_gettime_nsec_np|os_unfair_lock|os_sync_|dispatch_[A-Za-z0-9_]+|dyld|_NSGetExecutablePath)\b"),
    "posix": re.compile(r"\b(mmap|munmap|mprotect|pthread_|clock_gettime|open\(|read\(|write\(|poll\(|select\(|socket\(|recv|send|fcntl|stat\()",re.I),
    "sdl": re.compile(r"\bSDL_[A-Za-z0-9_]+\b"),
    "opengl": re.compile(r"\b(gl[A-Z][A-Za-z0-9_]*|GL_[A-Z0-9_]+|OpenGL)\b"),
    "freebsd_or_ps5": re.compile(r"\b(__FreeBSD__|PS5|PROSPERO|sceKernel|sceAudioOut|x86_64-sie-ps5)\b",re.I),
    "win32_hle": re.compile(r"\b(HLE|kernel32|user32|gdi32|wsock32|winmm|dsound|opengl32|CreateWindow|VirtualAlloc|GetProcAddress)\b",re.I),
}

def census(root: Path) -> dict:
    root=root.resolve()
    if not root.is_dir():
        raise ValueError(f"not a runtime directory: {root}")
    files=[]
    totals=Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        try:
            text=path.read_text(encoding="utf-8",errors="replace")
        except OSError:
            continue
        categories={}
        for name,rx in PATTERNS.items():
            count=len(rx.findall(text))
            if count:
                categories[name]=count
                totals[name]+=count
        files.append({
            "path":path.relative_to(root).as_posix(),
            "categories":categories,
            "apple_blocker":bool(categories.get("apple_framework") or categories.get("darwin_api")),
            "ps5_marker_present":bool(categories.get("freebsd_or_ps5")),
        })
    apple=[x["path"] for x in files if x["apple_blocker"]]
    candidates=[x["path"] for x in files if not x["apple_blocker"]]
    return {
        "schema":1,
        "runtime_root":None,
        "source_files":len(files),
        "category_totals":dict(sorted(totals.items())),
        "apple_blocker_files":apple,
        "apple_blocker_count":len(apple),
        "non_apple_candidate_files":candidates,
        "non_apple_candidate_count":len(candidates),
        "files":files,
        "note":"Static lexical evidence only; candidate files are not compiler- or device-qualified.",
    }

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("runtime",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        report=census(a.runtime)
    except (ValueError,OSError) as exc:
        p.error(str(exc))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"runtime sources={report['source_files']} apple_blockers={report['apple_blocker_count']} non_apple_candidates={report['non_apple_candidate_count']}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
