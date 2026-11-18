#!/usr/bin/env python3
"""Build a fail-closed private PS5 recompilation plan from sanitized Warcraft reports.

Inputs are JSON reports produced by the repository's private/local tools. No game
bytes are read here. The planner intentionally refuses to claim build readiness
without a known executable architecture, recognized content layout, a passing
first-launch runtime gate, and a qualified graphics receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

WIN64_LIFTER = {
    "id": "nightsight_recomp64",
    "framework_commit": "63742ed02e039b292bbf341a33b3bb8c73457fea",
    "private_wrapper": "scripts/ps5/private_win64_lift.py",
}
WIN32_LIFTER = {
    "id": "refrozen_x86recomp",
    "scope": "version_specific_manifests_required",
    "private_wrapper": "scripts/lift.sh",
}

ENTRY_NAMES = (
    "warcraft iii.exe",
    "war3.exe",
    "frozen throne.exe",
)


class PlanError(ValueError):
    pass


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read JSON report {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError(f"{path.name}: report root must be an object")
    return data


def _entry_candidates(census: dict) -> list[dict]:
    results = [x for x in census.get("results", []) if isinstance(x, dict) and "error" not in x]
    exes = [x for x in results if str(x.get("file", "")).lower().endswith(".exe")]
    ranked = []
    for item in exes:
        name = str(item.get("file", "")).lower()
        try:
            rank = ENTRY_NAMES.index(name)
        except ValueError:
            rank = len(ENTRY_NAMES)
        ranked.append((rank, name, item))
    return [item for _, _, item in sorted(ranked, key=lambda x: (x[0], x[1]))]


def _select_entry(census: dict, explicit: str | None) -> tuple[dict | None, list[str]]:
    candidates = _entry_candidates(census)
    if explicit:
        matches = [
            item for item in candidates
            if str(item.get("relative_file") or item.get("file", "")).casefold()
            == explicit.casefold()
            or str(item.get("file", "")).casefold() == explicit.casefold()
        ]
        if len(matches) != 1:
            return None, [f"requested entry {explicit!r} did not resolve uniquely"]
        return matches[0], []
    known = [
        item for item in candidates
        if str(item.get("file", "")).casefold() in ENTRY_NAMES
    ]
    if len(known) == 1:
        return known[0], []
    if len(candidates) == 1:
        return candidates[0], []
    if not candidates:
        return None, ["no executable PE found in install census"]
    return None, ["multiple executable PEs found; select the game entry explicitly"]


def _lifter(entry: dict | None) -> tuple[dict | None, list[str]]:
    if not entry:
        return None, ["entry executable unresolved"]
    machine, bits = entry.get("machine"), entry.get("pe_bits")
    if machine == "x86_64" and bits == 64:
        return dict(WIN64_LIFTER), []
    if machine == "x86" and bits == 32:
        return dict(WIN32_LIFTER), []
    return None, [f"unsupported executable architecture: {machine} PE{bits}"]


def _renderer(entry: dict | None) -> tuple[dict, list[str]]:
    profile = (entry or {}).get("graphics_profile") or {}
    route = profile.get("ps5_initial_route")
    static = profile.get("static_backends") or []
    if route == "opengl_wgl_to_ps5_egl":
        return {
            "route": "wgl_egl",
            "source": "static_opengl_import",
            "static_backends": static,
        }, []
    if route == "renderer_translation_or_runtime_forcing_required":
        return {
            "route": None,
            "source": "non_opengl_static_renderer",
            "static_backends": static,
        }, ["static graphics imports do not select the qualified WGL/EGL route"]
    return {
        "route": None,
        "source": "undetermined",
        "static_backends": static,
    }, ["graphics route not proven by the entry executable census"]


def _content(census: dict) -> tuple[dict, list[str]]:
    layout = census.get("storage_layout") or {}
    kind = layout.get("classification", "unknown")
    supported = {"legacy_mpq", "casc", "mixed_casc_and_legacy_mpq"}
    errors = [] if kind in supported else [f"unrecognized/partial Warcraft content layout: {kind}"]
    return {
        "classification": kind,
        "route": (
            "legacy_mpq_reader" if kind == "legacy_mpq"
            else "casc_reader" if kind == "casc"
            else "casc_plus_mpq_compat" if kind == "mixed_casc_and_legacy_mpq"
            else None
        ),
    }, errors


def _graphics_receipt(receipt: dict | None) -> tuple[dict, list[str]]:
    if receipt is None:
        return {"qualified": False, "receipt": None}, [
            "registered PPSA99006 WGL/OpenGL hardware receipt not supplied"
        ]

    passed = receipt.get("pass")
    if passed is None:
        passed = receipt.get("passed")
    sha = receipt.get("eboot_sha256") or receipt.get("sha256")
    sha_ok = (
        isinstance(sha, str)
        and len(sha) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in sha)
    )

    # Accept either an explicit probe identity or the exact terminal receipt
    # shape emitted by scripts/ps5/verify-wgl-title-receipt.py on PR #60.
    marker = receipt.get("marker") or receipt.get("event") or ""
    terminal = str(receipt.get("terminal_line") or "")
    identity_ok = (
        receipt.get("probe") == "PPSA99006"
        or "REFROZEN_PS5_WGL_TITLE" in str(marker)
        or terminal.startswith("REFROZEN_PS5_WGL_TITLE pass=1 ")
    )
    semantic_ok = True
    if terminal:
        semantic_ok = (
            receipt.get("frames") == 120
            and receipt.get("clear") is True
            and receipt.get("delete") is True
            and int(receipt.get("width") or 0) > 0
            and int(receipt.get("height") or 0) > 0
        )

    qualified = bool(passed is True or passed == 1) and sha_ok and identity_ok and semantic_ok
    return {
        "qualified": qualified,
        "receipt": {
            "probe": receipt.get("probe") or ("PPSA99006" if identity_ok else None),
            "marker": marker or ("REFROZEN_PS5_WGL_TITLE" if terminal else None),
            "terminal_line": terminal or None,
            "eboot_sha256": sha.lower() if sha_ok else sha,
        },
    }, [] if qualified else ["graphics hardware receipt is missing, malformed, or not passing"]


def _map_summary(reports: list[dict]) -> dict:
    langs = Counter()
    native = 0
    hints = Counter()
    for report in reports:
        profile = report.get("script_profile") or {}
        if profile.get("has_jass"):
            langs["jass"] += 1
        if profile.get("has_lua"):
            langs["lua"] += 1
        if (report.get("embedded_native_code") or {}).get("present"):
            native += 1
        hint = profile.get("engine_hint")
        if hint:
            hints[str(hint)] += 1
    return {
        "reports": len(reports),
        "script_languages": dict(sorted(langs.items())),
        "engine_hints": dict(sorted(hints.items())),
        "embedded_native_code_warnings": native,
        "note": "map census is advisory; original maps still require runtime/determinism tests",
    }


def build_plan(
    census: dict,
    runtime_gate: dict,
    graphics_receipt: dict | None = None,
    map_reports: list[dict] | None = None,
    entry_name: str | None = None,
) -> dict:
    blockers: list[str] = []
    entry, errors = _select_entry(census, entry_name)
    blockers += errors
    lifter, errors = _lifter(entry)
    blockers += errors
    renderer, errors = _renderer(entry)
    blockers += errors
    content, errors = _content(census)
    blockers += errors
    graphics, errors = _graphics_receipt(graphics_receipt)
    blockers += errors

    runtime_passed = runtime_gate.get("passed") is True
    if not runtime_passed:
        blockers.append("first-launch runtime gate is not PASS")

    if renderer.get("route") == "wgl_egl":
        external = set(runtime_gate.get("external_routes_proven") or [])
        if "wgl_egl" not in external:
            blockers.append("runtime gate did not record the wgl_egl external route")

    version = (entry or {}).get("version_resource")
    authoritative_hash = (entry or {}).get("sha256")
    maps = _map_summary(map_reports or [])

    unique_blockers = sorted(set(blockers))
    ready = not unique_blockers
    return {
        "schema": 1,
        "status": "ready_for_private_lift_and_link" if ready else "blocked",
        "privacy": "sanitized metadata only; no Warcraft file bytes or absolute paths",
        "entry": None if entry is None else {
            "file": entry.get("file"),
            "relative_file": entry.get("relative_file"),
            "sha256": authoritative_hash,
            "machine": entry.get("machine"),
            "pe_bits": entry.get("pe_bits"),
            "version_resource": version,
        },
        "lifter": lifter,
        "renderer": renderer,
        "graphics_hardware": graphics,
        "content": content,
        "runtime_gate": {
            "passed": runtime_passed,
            "missing_compile_routes": len(runtime_gate.get("missing_compile_routes") or []),
            "unresolved_imports": len(runtime_gate.get("unresolved_imports") or []),
            "external_routes_proven": sorted(runtime_gate.get("external_routes_proven") or []),
        },
        "maps": maps,
        "blockers": unique_blockers,
        "next_actions": (
            [
                "run the selected private lifter under repository /private",
                "compile generated code with the PS5 runtime and pinned SDK",
                "link a private Warcraft PS5 candidate",
                "test boot/menu/solo/campaign/save/custom-map/LAN in that order",
            ]
            if ready
            else [
                "resolve each blocker without weakening the fail-closed gates",
                "regenerate this plan from fresh sanitized reports",
            ]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path)
    parser.add_argument("runtime_gate", type=Path)
    parser.add_argument("--graphics-receipt", type=Path)
    parser.add_argument("--map-report", action="append", type=Path, default=[])
    parser.add_argument("--entry", help="relative path or basename of the game executable")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        plan = build_plan(
            _load(args.census),
            _load(args.runtime_gate),
            _load(args.graphics_receipt) if args.graphics_receipt else None,
            [_load(path) for path in args.map_report],
            args.entry,
        )
    except PlanError as exc:
        parser.error(str(exc))

    payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if plan["status"] == "ready_for_private_lift_and_link" else 1


if __name__ == "__main__":
    raise SystemExit(main())
