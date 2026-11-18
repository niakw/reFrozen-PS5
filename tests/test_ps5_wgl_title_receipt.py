import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ps5" / "verify-wgl-title-receipt.py"
spec = importlib.util.spec_from_file_location("verify_wgl_receipt", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class WglReceiptTest(unittest.TestCase):
    def test_latest_success_receipt(self):
        text = """
noise
REFROZEN_PS5_WGL_TITLE pass=0 stage=old-run gl_error=0x500
REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 (Compatibility Profile) Mesa PS5 renderer=PS5 OpenGL Driver width=1920 height=1080 frames=120 clear=1 delete=1
"""
        report = mod.parse_terminal_receipt(text)
        self.assertTrue(report["passed"])
        self.assertEqual(report["frames"], 120)
        self.assertEqual(report["width"], 1920)
        self.assertEqual(report["height"], 1080)
        self.assertEqual(report["receipt_count"], 2)
        self.assertEqual(report["renderer"], "PS5 OpenGL Driver")

    def test_terminal_failure_wins(self):
        text = """
REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 renderer=PS5 width=1920 height=1080 frames=120 clear=1 delete=1
REFROZEN_PS5_WGL_TITLE pass=0 stage=swap gl_error=0x0
"""
        with self.assertRaises(mod.ReceiptError):
            mod.parse_terminal_receipt(text)

    def test_rejects_short_or_dirty_teardown(self):
        bad = [
            "REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 renderer=PS5 width=1920 height=1080 frames=119 clear=1 delete=1",
            "REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 renderer=PS5 width=1920 height=1080 frames=120 clear=0 delete=1",
            "REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 renderer=PS5 width=0 height=1080 frames=120 clear=1 delete=1",
        ]
        for line in bad:
            with self.subTest(line=line):
                with self.assertRaises(mod.ReceiptError):
                    mod.parse_terminal_receipt(line)

    def test_sha256_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "eboot.bin"
            path.write_bytes(b"registered-title-fixture")
            self.assertEqual(
                mod.sha256_file(path),
                hashlib.sha256(b"registered-title-fixture").hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
