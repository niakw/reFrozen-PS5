"""Synthetic tests for Win64 runtime host-dependency triage."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.win64_runtime_portability import audit_runtime


class Win64RuntimePortabilityTest(unittest.TestCase):
    def test_classifies_host_specific_and_portable_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runtime"
            root.mkdir()
            (root / "rt.c").write_text(
                '#include <mach/mach.h>\n'
                '#include <pthread.h>\n'
                'void x(void) { pthread_mutex_lock(0); }\n',
                encoding="utf-8",
            )
            (root / "fiber.c").write_text(
                'void x(void) { __asm__ volatile("sub sp, sp, #16\\n" '
                '"stp x19, x20, [sp]\\n"); }\n',
                encoding="utf-8",
            )
            (root / "files.c").write_text(
                '#include <copyfile.h>\nvoid x(void) { copyfile(0,0,0,0); }\n',
                encoding="utf-8",
            )
            (root / "portable.c").write_text(
                '#include <sys/socket.h>\n'
                'void x(void) { (void)socket(2, 1, 0); }\n',
                encoding="utf-8",
            )
            report = audit_runtime(root)
            by_path = {item["path"]: item for item in report["files"]}
            self.assertIn("mach_api", by_path["rt.c"]["blockers"])
            self.assertIn("arm64_context_asm", by_path["fiber.c"]["blockers"])
            self.assertIn("darwin_only_api", by_path["files.c"]["blockers"])
            self.assertEqual(by_path["portable.c"]["blockers"], {})
            self.assertEqual(
                by_path["portable.c"]["portability_class"], "portable_candidate")
            self.assertIsNone(report["root"])
            self.assertNotIn(str(root), str(report))

    def test_rejects_missing_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                audit_runtime(Path(temp) / "missing")


if __name__ == "__main__":
    unittest.main()
