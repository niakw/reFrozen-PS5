#!/usr/bin/env python3
"""Private Win64 PE -> generated C wrapper for user-owned Warcraft files.

Generated code is derivative of the supplied executable and MUST stay under the
repository's git-ignored /private tree. This wrapper records only sanitized
metadata and never uploads, commits, or copies the source PE.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

from scripts.ps5.pe_probe import inspect_pe, PEFormatError

PINNED_NIGHTSIGHT = "63742ed02e039b292bbf341a33b3bb8c73457fea"


class PrivateLiftError(ValueError):
    pass


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_output(repo_root: Path, output: Path) -> tuple[Path, Path]:
    repo_root = repo_root.resolve()
    private_root = (repo_root / "private").resolve()
    output = output.resolve()
    if output == private_root or not _inside(output, private_root):
        raise PrivateLiftError("generated output must be a child of repository /private")
    if output.exists() and output.is_symlink():
        raise PrivateLiftError("generated output must not be a symlink")
    return private_root, output


def validate_lifter(lifter_root: Path) -> Path:
    lifter_root = lifter_root.resolve()
    script = lifter_root / "tools" / "recomp64.py"
    if not script.is_file():
        raise PrivateLiftError("NightSight tools/recomp64.py not found")
    return script


def parse_unsupported(log_text: str) -> dict[str, int] | None:
    prefix = "UNSUPPORTED:"
    for line in reversed(log_text.splitlines()):
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return None
            if not isinstance(parsed, dict):
                return None
            clean = {}
            for key, count in parsed.items():
                if not isinstance(key, str) or not isinstance(count, int):
                    return None
                clean[key] = count
            return dict(sorted(clean.items()))
    return None


def lift_private(
    executable: Path,
    lifter_root: Path,
    output: Path,
    repo_root: Path,
    python: str = sys.executable,
) -> dict:
    executable = executable.resolve()
    if not executable.is_file():
        raise PrivateLiftError("input executable does not exist")

    private_root, output = validate_output(repo_root, output)
    lifter = validate_lifter(lifter_root)

    try:
        pe = inspect_pe(executable)
    except (PEFormatError, OSError) as exc:
        raise PrivateLiftError(f"input PE rejected: {exc}") from exc
    if pe.get("pe_bits") != 64 or pe.get("machine") != "x86_64":
        raise PrivateLiftError(
            f"Win64 lifter requires x86_64 PE32+; observed "
            f"{pe.get('machine')} PE{pe.get('pe_bits')}"
        )

    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not _inside(output.resolve(), private_root):
        raise PrivateLiftError("output escaped /private after creation")

    generated = output / "generated"
    generated.mkdir(exist_ok=True)
    log_path = output / "translation.log"

    command = [python, str(lifter), str(executable), str(generated)]
    completed = subprocess.run(
        command,
        cwd=lifter_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")

    unsupported = parse_unsupported(completed.stdout)
    code_files = sorted(generated.glob("code_*.c"))
    report = {
        "schema": 1,
        "status": "ok" if completed.returncode == 0 and code_files else "failed",
        "privacy": (
            "input path omitted; generated game-derived code stays under git-ignored /private"
        ),
        "input": {
            "file": pe["file"],
            "sha256": pe["sha256"],
            "machine": pe["machine"],
            "pe_bits": pe["pe_bits"],
            "image_base": pe["image_base"],
            "image_size": pe["image_size"],
            "version_resource": pe.get("version_resource"),
            "import_dll_count": pe.get("import_dll_count"),
            "import_symbol_count": pe.get("import_symbol_count"),
        },
        "lifter": {
            "expected_framework_commit": PINNED_NIGHTSIGHT,
            "root_recorded": None,
        },
        "translation": {
            "returncode": completed.returncode,
            "generated_code_files": len(code_files),
            "unsupported": unsupported,
            "unsupported_total": (
                sum(unsupported.values()) if unsupported is not None else None
            ),
            "log": "translation.log",
            "generated_dir": "generated",
        },
    }
    (output / "lift-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if completed.returncode != 0:
        raise PrivateLiftError(
            f"lifter failed with exit code {completed.returncode}; see private translation.log"
        )
    if not code_files:
        raise PrivateLiftError("lifter returned success but generated no code_*.c files")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("executable", type=Path)
    parser.add_argument(
        "--lifter-root", required=True, type=Path,
        help="local checkout of the pinned NightSight Recomp-Framework",
    )
    parser.add_argument(
        "--output", type=Path,
        default=repo_root / "private" / "warcraft-win64-lift",
    )
    args = parser.parse_args()
    try:
        report = lift_private(
            args.executable, args.lifter_root, args.output, repo_root
        )
    except (OSError, PrivateLiftError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
