"""Synthetic WGL PE structure tests; no proprietary bytes."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.synthetic_pe64_wgl import make_pe64_wgl, IMPORTS
from scripts.ps5.pe_probe import inspect_pe


class SyntheticWglPeTest(unittest.TestCase):
    def test_pe64_shape_and_import_strings(self):
        binary = make_pe64_wgl()
        self.assertEqual(len(binary), 0x1000)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wgl.exe"
            path.write_bytes(binary)
            info = inspect_pe(path)
            self.assertEqual(info["machine"], "x86_64")
            self.assertEqual(info["pe_bits"], 64)
            self.assertEqual(
                info["sections"],
                [".text", ".data", ".rdata", ".idata", ".pdata", ".xdata"],
            )
        self.assertIn(b"OPENGL32.dll\0", binary)
        for name in IMPORTS:
            self.assertIn(name.encode("ascii") + b"\0", binary)
        self.assertIn(b"glGetString\0", binary)
        self.assertEqual(make_pe64_wgl(), binary)


if __name__ == "__main__":
    unittest.main()
