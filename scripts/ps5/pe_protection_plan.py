#!/usr/bin/env python3
"""Plan coarse PS5 host protections for an identity-mapped translated PE image.

Translated guest code executes from native C/C++ code, never from the guest PE
.text bytes. Therefore the guest image is deliberately never host-executable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_GRANULE = 0x4000


class ProtectionPlanError(ValueError):
    pass


def _prot(read: bool, write: bool) -> str:
    return ("r" if read else "-") + ("w" if write else "-") + "-"


def plan_module(module: dict, granule: int = DEFAULT_GRANULE) -> dict:
    if granule <= 0 or granule & (granule - 1):
        raise ProtectionPlanError("granule must be a power of two")
    base = int(module["image_base"], 0)
    size = int(module["image_size"])
    headers = int(module.get("size_of_headers", 0))
    if not size or base & (granule - 1):
        raise ProtectionPlanError("image base/size incompatible with exact granule mapping")
    end = base + size
    if end <= base:
        raise ProtectionPlanError("image range overflow")

    pages: dict[int, list[dict]] = {}

    def add_range(start: int, length: int, source: str,
                  read: bool, write: bool, execute: bool) -> None:
        if not length:
            return
        stop = start + length
        if start < base or stop > end or stop <= start:
            raise ProtectionPlanError(f"{source} lies outside PE image")
        page = start & ~(granule - 1)
        while page < stop:
            pages.setdefault(page, []).append({
                "source": source,
                "read": read,
                "write": write,
                "execute": execute,
            })
            page += granule

    if headers:
        add_range(base, min(headers, size), "PE headers", True, False, False)

    for section in module.get("section_details", []):
        span = max(int(section.get("virtual_size", 0)), int(section.get("raw_size", 0)))
        if not span:
            continue
        add_range(
            base + int(section["virtual_address"]),
            span,
            section["name"],
            bool(section.get("read")),
            bool(section.get("write")),
            bool(section.get("execute")),
        )

    planned = []
    broadened = []
    guest_execute = []
    for address in sorted(pages):
        sources = pages[address]
        # Host memory is data-only. Write permission is needed if any guest
        # section sharing the 16 KiB granule is writable. Read is required for
        # every populated guest image granule.
        host_write = any(item["write"] for item in sources)
        host_read = True
        ro_sources = sorted({item["source"] for item in sources if not item["write"]})
        rw_sources = sorted({item["source"] for item in sources if item["write"]})
        exec_sources = sorted({item["source"] for item in sources if item["execute"]})
        write_broadened = host_write and bool(ro_sources)
        if write_broadened:
            broadened.append(f"0x{address:x}")
        if exec_sources:
            guest_execute.append(f"0x{address:x}")
        planned.append({
            "address": address,
            "host_protection": _prot(host_read, host_write),
            "host_execute": False,
            "guest_execute_sources": exec_sources,
            "read_only_sources": ro_sources,
            "writable_sources": rw_sources,
            "coarse_write_broadening": write_broadened,
        })

    segments = []
    for page in planned:
        key = (page["host_protection"], page["coarse_write_broadening"],
               bool(page["guest_execute_sources"]))
        if segments and segments[-1]["_key"] == key and \
                segments[-1]["end"] == page["address"]:
            segments[-1]["end"] += granule
            segments[-1]["granules"] += 1
        else:
            segments.append({
                "_key": key,
                "start": page["address"],
                "end": page["address"] + granule,
                "granules": 1,
                "host_protection": page["host_protection"],
                "host_execute": False,
                "coarse_write_broadening": page["coarse_write_broadening"],
                "contains_guest_executable_bytes": bool(page["guest_execute_sources"]),
            })
    for segment in segments:
        segment.pop("_key", None)
        segment["start"] = f"0x{segment['start']:x}"
        segment["end"] = f"0x{segment['end']:x}"

    return {
        "schema": 1,
        "file": module.get("file"),
        "image_base": module["image_base"],
        "image_size": size,
        "granule": granule,
        "host_execution_policy": "never execute guest PE image bytes; translated native code executes elsewhere",
        "segments": segments,
        "coarse_write_broadening_granules": broadened,
        "guest_executable_byte_granules": guest_execute,
        "requires_guest_4k_protection_model_for_exact_windows_semantics": bool(broadened),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path, help="pe_probe.py or scan_install.py JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--granule", type=lambda x: int(x, 0), default=DEFAULT_GRANULE)
    args = parser.parse_args()
    census = json.loads(args.census.read_text(encoding="utf-8"))
    plans = []
    failed = []
    for module in census.get("results", []):
        if "error" in module:
            continue
        try:
            plans.append(plan_module(module, args.granule))
        except (KeyError, TypeError, ValueError, ProtectionPlanError) as exc:
            failed.append({"file": module.get("file"), "error": str(exc)})
    result = {"schema": 1, "plans": plans, "failed": failed}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
