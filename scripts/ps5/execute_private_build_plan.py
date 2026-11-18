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


def _verify_planned_pe(planned: dict, path: Path, label: str) -> dict:
    try:
        observed = inspect_pe(path)
    except (OSError, PEFormatError) as exc:
        raise PlanExecutionError(f"{label} PE rejected: {exc}") from exc

    expected_sha = str(planned.get("sha256") or "").lower()
    observed_sha = str(observed.get("sha256") or "").lower()
    if len(expected_sha) != 64 or observed_sha != expected_sha:
        raise PlanExecutionError(f"{label} SHA-256 does not match the private build plan")
    if (
        observed.get("machine") != planned.get("machine")
        or observed.get("pe_bits") != planned.get("pe_bits")
    ):
        raise PlanExecutionError(f"{label} architecture differs from the private build plan")
    expected_name = str(planned.get("file") or "")
    if expected_name and path.name.casefold() != expected_name.casefold():
        raise PlanExecutionError(
            f"{label} basename {path.name!r} differs from planned {expected_name!r}"
        )
    return observed


def _resolve_install_module(install_root: Path, relative_file: object) -> Path:
    if not isinstance(relative_file, str) or not relative_file:
        raise PlanExecutionError("planned local module has no relative_file")
    normalized = relative_file.replace("\\", "/")
    rel = Path(normalized)
    if rel.is_absolute() or ".." in rel.parts:
        raise PlanExecutionError("planned local module path escapes install root")
    root = install_root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PlanExecutionError("planned local module path escapes install root") from exc
    if not candidate.is_file():
        raise PlanExecutionError(f"planned local module is missing: {relative_file}")
    return candidate


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
    install_root: Path | None = None,
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
    _verify_planned_pe(entry, executable, "input executable")
    expected_sha = str(entry.get("sha256") or "").lower()

    private_root = (repo_root.resolve() / "private")
    output = output.resolve()
    try:
        output.relative_to(private_root.resolve())
    except ValueError as exc:
        raise PlanExecutionError("output must stay under repository /private") from exc

    module_specs = plan.get("local_modules") or []
    if not isinstance(module_specs, list):
        raise PlanExecutionError("plan local_modules must be a list")
    if module_specs and install_root is None:
        raise PlanExecutionError("install_root is required for planned local modules")
    resolved_install = install_root.resolve() if install_root is not None else None
    if resolved_install is not None and not resolved_install.is_dir():
        raise PlanExecutionError("install_root is not a directory")

    # Verify the complete private input set before generating any derivative C.
    prepared_modules = []
    for index, spec in enumerate(module_specs):
        if not isinstance(spec, dict):
            raise PlanExecutionError("planned local module entry must be an object")
        assert resolved_install is not None
        module_path = _resolve_install_module(
            resolved_install, spec.get("relative_file")
        )
        _verify_planned_pe(spec, module_path, "local module")

        module_name = module_path.stem
        rebase = None
        if spec.get("rebase_required") is True:
            rebase = spec.get("rebase_arg")
            if not rebase:
                raise PlanExecutionError(
                    f"planned rebase is missing for local module {module_path.name}"
                )

        safe_stem = "".join(
            ch if ch.isalnum() or ch in "._-" else "_"
            for ch in module_name
        ).strip("._-") or "module"
        module_output = output / "modules" / f"{index:03d}-{safe_stem.lower()}"
        prepared_modules.append(
            (spec, module_path, module_name, rebase, module_output)
        )

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

    module_reports = []
    for spec, module_path, module_name, rebase, module_output in prepared_modules:
        try:
            module_lift = lift_private(
                module_path,
                lifter_root,
                module_output,
                repo_root,
                require_pinned_lifter=require_pinned_lifter,
                module_name=module_name,
                rebase=rebase,
            )
        except PrivateLiftError as exc:
            raise PlanExecutionError(
                f"local module {module_path.name}: {exc}"
            ) from exc
        module_reports.append({
            "file": spec.get("file"),
            "relative_file": spec.get("relative_file"),
            "sha256": str(spec.get("sha256") or "").lower(),
            "module_name": module_lift["input"].get("module_name"),
            "rebase": module_lift["input"].get("rebase"),
            "generated_code_files": (
                module_lift.get("translation") or {}
            ).get("generated_code_files"),
            "unsupported": (
                module_lift.get("translation") or {}
            ).get("unsupported"),
            "unsupported_total": (
                module_lift.get("translation") or {}
            ).get("unsupported_total"),
            "lift_report": str(
                (module_output / "lift-report.json").relative_to(output)
            ),
        })

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
        "modules": module_reports,
        "translation": {
            "generated_code_files": (lift.get("translation") or {}).get("generated_code_files"),
            "unsupported": (lift.get("translation") or {}).get("unsupported"),
            "unsupported_total": (lift.get("translation") or {}).get("unsupported_total"),
            "lift_report": "lift-report.json",
        },
        "next_gate": (
            "compile_and_link_generated_entry_and_modules_for_ps5"
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
        "--install-root", type=Path,
        help="local Warcraft install root; required when the plan contains local_modules",
    )
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
            install_root=args.install_root,
        )
    except (OSError, PlanExecutionError) as exc:
        parser.error(str(exc))

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "lift_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
