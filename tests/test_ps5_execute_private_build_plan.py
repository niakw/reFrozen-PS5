from pathlib import Path
import hashlib
import tempfile
import unittest

from scripts.ps5.execute_private_build_plan import (
    PlanExecutionError,
    execute_plan,
)
from scripts.ps5.synthetic_pe64 import make_pe64


def ready_plan(sha: str, file_name="Warcraft III.exe"):
    return {
        "status": "ready_for_private_lift_and_link",
        "entry": {
            "file": file_name,
            "sha256": sha,
            "machine": "x86_64",
            "pe_bits": 64,
        },
        "lifter": {
            "id": "nightsight_recomp64",
            "framework_commit": "63742ed02e039b292bbf341a33b3bb8c73457fea",
        },
    }


class ExecutePrivateBuildPlanTest(unittest.TestCase):
    def _fixture(self, temp: str):
        root = Path(temp) / "repo"
        (root / "private").mkdir(parents=True)
        owned = Path(temp) / "owned"
        owned.mkdir()
        exe = owned / "Warcraft III.exe"
        data = make_pe64()
        exe.write_bytes(data)

        lifter = Path(temp) / "lifter"
        (lifter / "tools").mkdir(parents=True)
        (lifter / "tools" / "recomp64.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "out=Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)\n"
            "(out/'code_0000.c').write_text('void F_140001000(void) {}\\n')\n"
            "(out/'tables.c').write_text('/* fixture */\\n')\n"
            "(out/'args.txt').write_text(' '.join(sys.argv[3:]))\n"
            "print('translated 1 functions')\n"
            "print('UNSUPPORTED: {}')\n",
            encoding="utf-8",
        )
        sha = hashlib.sha256(data).hexdigest()
        return root, exe, lifter, sha

    def test_exact_sha_executes_private_lift(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            output = root / "private" / "lift"
            report = execute_plan(
                ready_plan(sha),
                exe,
                lifter,
                output,
                repo_root=root,
                require_pinned_lifter=False,
            )
            self.assertEqual(report["status"], "lift_complete")
            self.assertEqual(report["plan_entry"]["sha256"], sha)
            self.assertEqual(report["translation"]["unsupported_total"], 0)
            self.assertTrue((output / "generated" / "code_0000.c").is_file())
            self.assertTrue((output / "plan-execution-report.json").is_file())
            self.assertNotIn(str(Path(temp) / "owned"), str(report))

    def test_exact_local_module_is_lifted_with_planned_rebase(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            install = Path(temp) / "install"
            module_dir = install / "x86_64"
            module_dir.mkdir(parents=True)
            module = module_dir / "Game.dll"
            data = make_pe64()
            module.write_bytes(data)
            module_sha = hashlib.sha256(data).hexdigest()

            plan = ready_plan(sha)
            plan["local_modules"] = [{
                "file": "Game.dll",
                "relative_file": "x86_64/Game.dll",
                "sha256": module_sha,
                "machine": "x86_64",
                "pe_bits": 64,
                "rebase_required": True,
                "rebase_arg": "0x180000000",
            }]
            output = root / "private" / "lift"
            report = execute_plan(
                plan, exe, lifter, output,
                repo_root=root, require_pinned_lifter=False,
                install_root=install,
            )
            self.assertEqual(report["status"], "lift_complete")
            self.assertEqual(len(report["modules"]), 1)
            module_report = report["modules"][0]
            self.assertEqual(module_report["file"], "Game.dll")
            self.assertEqual(module_report["sha256"], module_sha)
            self.assertEqual(module_report["rebase"], "0x180000000")
            args = (
                output / "modules" / "000-game" / "generated" / "args.txt"
            ).read_text()
            self.assertEqual(args, "--module Game --rebase 180000000")
            self.assertNotIn(str(install), str(report))

    def test_planned_modules_require_install_root_before_entry_lift(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            plan = ready_plan(sha)
            plan["local_modules"] = [{
                "file": "Game.dll",
                "relative_file": "Game.dll",
                "sha256": "c" * 64,
                "machine": "x86_64",
                "pe_bits": 64,
                "rebase_required": False,
            }]
            output = root / "private" / "lift"
            with self.assertRaisesRegex(PlanExecutionError, "install_root"):
                execute_plan(
                    plan, exe, lifter, output,
                    repo_root=root, require_pinned_lifter=False,
                )
            self.assertFalse((output / "generated").exists())

    def test_module_sha_mismatch_fails_before_any_lift(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            install = Path(temp) / "install"
            install.mkdir()
            module = install / "Game.dll"
            module.write_bytes(make_pe64())
            plan = ready_plan(sha)
            plan["local_modules"] = [{
                "file": "Game.dll",
                "relative_file": "Game.dll",
                "sha256": "0" * 64,
                "machine": "x86_64",
                "pe_bits": 64,
                "rebase_required": False,
            }]
            output = root / "private" / "lift"
            with self.assertRaisesRegex(PlanExecutionError, "local module SHA-256"):
                execute_plan(
                    plan, exe, lifter, output,
                    repo_root=root, require_pinned_lifter=False,
                    install_root=install,
                )
            self.assertFalse((output / "generated").exists())

    def test_module_relative_path_cannot_escape_install_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            install = Path(temp) / "install"
            install.mkdir()
            outside = Path(temp) / "Game.dll"
            outside.write_bytes(make_pe64())
            plan = ready_plan(sha)
            plan["local_modules"] = [{
                "file": "Game.dll",
                "relative_file": "../Game.dll",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "machine": "x86_64",
                "pe_bits": 64,
                "rebase_required": False,
            }]
            with self.assertRaisesRegex(PlanExecutionError, "escapes install root"):
                execute_plan(
                    plan, exe, lifter, root / "private" / "lift",
                    repo_root=root, require_pinned_lifter=False,
                    install_root=install,
                )

    def test_sha_mismatch_fails_before_lift(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            with self.assertRaisesRegex(PlanExecutionError, "SHA-256"):
                execute_plan(
                    ready_plan("0" * 64),
                    exe,
                    lifter,
                    root / "private" / "lift",
                    repo_root=root,
                    require_pinned_lifter=False,
                )

    def test_blocked_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            plan = ready_plan(sha)
            plan["status"] = "blocked"
            with self.assertRaisesRegex(PlanExecutionError, "not ready"):
                execute_plan(
                    plan, exe, lifter, root / "private" / "lift",
                    repo_root=root, require_pinned_lifter=False,
                )

    def test_wrong_lifter_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            plan = ready_plan(sha)
            plan["lifter"]["id"] = "refrozen_x86recomp"
            with self.assertRaisesRegex(PlanExecutionError, "supports only"):
                execute_plan(
                    plan, exe, lifter, root / "private" / "lift",
                    repo_root=root, require_pinned_lifter=False,
                )

    def test_basename_must_match_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            with self.assertRaisesRegex(PlanExecutionError, "basename"):
                execute_plan(
                    ready_plan(sha, file_name="war3.exe"),
                    exe,
                    lifter,
                    root / "private" / "lift",
                    repo_root=root,
                    require_pinned_lifter=False,
                )

    def test_output_cannot_escape_private(self):
        with tempfile.TemporaryDirectory() as temp:
            root, exe, lifter, sha = self._fixture(temp)
            with self.assertRaisesRegex(PlanExecutionError, "under repository /private"):
                execute_plan(
                    ready_plan(sha),
                    exe,
                    lifter,
                    root / "outside",
                    repo_root=root,
                    require_pinned_lifter=False,
                )


if __name__ == "__main__":
    unittest.main()
