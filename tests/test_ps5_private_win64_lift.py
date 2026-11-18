from pathlib import Path
import tempfile
import unittest

from scripts.ps5.private_win64_lift import (
    PrivateLiftError,
    lift_private,
    parse_unsupported,
    validate_output,
)
from scripts.ps5.synthetic_pe64 import make_pe64


class PrivateWin64LiftTest(unittest.TestCase):
    def test_parse_unsupported(self):
        self.assertEqual(
            parse_unsupported("x\nUNSUPPORTED: {'avx': 2, 'foo': 1}\n"),
            {"avx": 2, "foo": 1},
        )
        self.assertEqual(parse_unsupported("UNSUPPORTED: {}\n"), {})
        self.assertIsNone(parse_unsupported("no census\n"))
        self.assertIsNone(parse_unsupported("UNSUPPORTED: nope\n"))

    def test_output_must_stay_under_private(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "private").mkdir()
            _, good = validate_output(repo, repo / "private" / "lift")
            self.assertEqual(good, (repo / "private" / "lift").resolve())
            with self.assertRaises(PrivateLiftError):
                validate_output(repo, repo / "generated")
            with self.assertRaises(PrivateLiftError):
                validate_output(repo, repo / "private")

    def test_synthetic_private_lift_omits_input_path(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            (repo / "private").mkdir(parents=True)
            source = Path(temp) / "owned"
            source.mkdir()
            exe = source / "classic64.exe"
            exe.write_bytes(make_pe64())

            lifter = Path(temp) / "lifter"
            (lifter / "tools").mkdir(parents=True)
            (lifter / "tools" / "recomp64.py").write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "out=Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)\n"
                "(out/'code_0000.c').write_text('void F_140001000(void) {}\\n')\n"
                "(out/'tables.c').write_text('/* fixture */\\n')\n"
                "print('translated 1 functions')\n"
                "print('UNSUPPORTED: {}')\n",
                encoding="utf-8",
            )

            output = repo / "private" / "lift"
            report = lift_private(
                exe, lifter, output, repo, require_pinned_lifter=False
            )
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["translation"]["generated_code_files"], 1)
            self.assertEqual(report["translation"]["unsupported"], {})
            self.assertEqual(report["input"]["file"], "classic64.exe")
            self.assertEqual(report["input"]["pe_bits"], 64)
            self.assertNotIn(str(source), str(report))
            self.assertNotIn(str(lifter), str(report))
            self.assertTrue((output / "generated" / "code_0000.c").is_file())
            self.assertTrue((output / "lift-report.json").is_file())

    def test_missing_lifter_fails_before_translation(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            (repo / "private").mkdir(parents=True)
            exe = Path(temp) / "guest.exe"
            exe.write_bytes(make_pe64())
            with self.assertRaises(PrivateLiftError):
                lift_private(
                    exe, Path(temp) / "missing",
                    repo / "private" / "lift", repo,
                    require_pinned_lifter=False,
                )


    def test_unpinned_lifter_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            (repo / "private").mkdir(parents=True)
            exe = Path(temp) / "guest.exe"
            exe.write_bytes(make_pe64())
            lifter = Path(temp) / "lifter"
            (lifter / "tools").mkdir(parents=True)
            (lifter / "tools" / "recomp64.py").write_text(
                "print('fixture')\n", encoding="utf-8"
            )
            with self.assertRaises(PrivateLiftError):
                lift_private(
                    exe, lifter, repo / "private" / "lift", repo,
                    require_pinned_lifter=True,
                )


if __name__ == "__main__":
    unittest.main()
