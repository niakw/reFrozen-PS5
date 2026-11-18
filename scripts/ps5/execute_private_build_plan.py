#!/usr/bin/env python3
"""Execute a READY private Warcraft Win64 recompilation plan against one exact PE.

The executable must match the SHA-256 recorded in the sanitized plan. Generated
code remains under repository /private and is never uploaded by this tool.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ps5.pe_probe import inspect_pe, PEFormatError
from scripts.ps5.private_win64_lift import (
    PrivateLiftError,
    lift_private,
)


class PlanExecutionError(ValueError):
    pass


def _load_plan(path: Path) -> dict:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanExecutionError(f"cannot read plan {path.name}: {exc}") from exc
    if not isinstance(plan, dict):
        raise PlanExecutionError("plan root must be an object")
    return plan


def execute_plan(
    plan: dict,
    executable: Path,
    lifter_root: Path,
    output: Path,
    repo_root: Path = REPO_ROOT,
    require_pinned_lifter: bool = True,
) -> dict:
    if plan.get("status") != "ready_for_private_lift_and_link":
        raise PlanExecutionError("plan is not ready_for_private_lift_and_link")

    entry = plan.get("entry")
    lifter = plan.get("lifter")
    if not isinstance(entry, dict) or not isinstance(lifter, dict):
        raise PlanExecutionError("plan entry/lifter metadata is missing")
    if lifter.get("id") != "nightsight_recomp64":
        raise PlanExecutionError(
            f"executor currently supports only nightsight_recomp64; plan selected {lifter.get('id')!r}"
        )

    executable = executable.resolve()
    try:
        observed = inspect_pe(executable)
    except (OSError, PEFormatError) as exc:
        raise PlanExecutionError(f"input PE rejected: {exc}") from exc

    expected_sha = str(entry.get("sha256") or "").lower()
    observed_sha = str(observed.get("sha256") or "").lower()
    if len(expected_sha) != 64 or observed_sha != expected_sha:
        raise PlanExecutionError(
            "input executable SHA-256 does not match the private build plan"
        )
    if observed.get("machine") != entry.get("machine") or observed.get("pe_bits") != entry.get("pe_bits"):
        raise PlanExecutionError("input executable architecture differs from the private build plan")

    expected_name = str(entry.get("file") or "")
    if expected_name and executable.name.casefold() != expected_name.casefold():
        raise PlanExecutionError(
            f"input basename {executable.name!r} differs from planned entry {expected_name!r}"
        )

    private_root = (repo_root.resolve() / "private")
    output = output.resolve()
    try:
        output.relative_to(private_root.resolve())
    except ValueError as exc:
        raise PlanExecutionError("output must stay under repository /private") from exc

    try:
        lift = lift_private(
            executable,
            lifter_root,
            output,
            repo_root,
            require_pinned_lifter=require_pinned_lifter,
        )
    except PrivateLiftError as exc:
        raise PlanExecutionError(str(exc)) from exc

    report = {
        "schema": 1,
        "status": "lift_complete" if lift.get("status") == "ok" else "failed",
        "privacy": "game path omitted; generated code remains under repository /private",
        "plan_entry": {
            "file": entry.get("file"),
            "sha256": expected_sha,
            "machine": entry.get("machine"),
            "pe_bits": entry.get("pe_bits"),
        },
        "lifter": {
            "id": lifter.get("id"),
            "framework_commit": lifter.get("framework_commit"),
        },
        "translation": {
            "generated_code_files": (lift.get("translation") or {}).get("generated_code_files"),
            "unsupported": (lift.get("translation") or {}).get("unsupported"),
            "unsupported_total": (lift.get("translation") or {}).get("unsupported_total"),
            "lift_report": "lift-report.json",
        },
        "next_gate": (
            "compile_and_link_generated_code_for_ps5"
            if lift.get("status") == "ok"
            else "fix_private_lift"
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan-execution-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--lifter-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "private" / "warcraft-win64-lift",
    )
    args = parser.parse_args()

    try:
        report = execute_plan(
            _load_plan(args.plan),
            args.executable,
            args.lifter_root,
            args.output,
        )
    except (OSError, PlanExecutionError) as exc:
        parser.error(str(exc))

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "lift_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
