"""Ensure the Win64 recomp fixture is deterministic and nonproprietary."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.synthetic_pe64 import make_pe64
from scripts.ps5.pe_probe import inspect_pe


class SyntheticPE64Test(unittest.TestCase):
    def test_structure(self):
        binary = make_pe64()
        self.assertEqual(len(binary), 0x800)
        self.assertEqual(binary[0x200:0x206], b"\xB8\x2A\x00\x00\x00\xC3")
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "tiny_win64.exe"
            p.write_bytes(binary)
            info = inspect_pe(p)
            self.assertEqual(info["machine"], "x86_64")
            self.assertEqual(info["pe_bits"], 64)
            self.assertEqual(info["image_base"], "0x140000000")
            self.assertEqual(info["sections"], [".text", ".pdata", ".xdata"])
            self.assertEqual(info["sha256"], hashlib.sha256(binary).hexdigest())
            self.assertEqual(make_pe64(), binary)


if __name__ == "__main__":
    unittest.main()
