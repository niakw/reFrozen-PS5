"""Synthetic Win64 five-argument import fixture tests."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe
from scripts.ps5.synthetic_pe64_abi5_import import make_pe64_abi5_import


class SyntheticPE64Abi5ImportTest(unittest.TestCase):
    def test_writefile_import_and_code_shape(self):
        data = make_pe64_abi5_import()
        self.assertEqual(len(data), 0xE00)
        self.assertEqual(data[0x400:0x404], b"\x48\x83\xEC\x38")
        self.assertIn(b"\x48\xC7\x44\x24\x20\x55\x55\x00\x00",
                      data[0x400:0x435])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "abi5.exe"
            path.write_bytes(data)
            info = inspect_pe(path)
            self.assertEqual(info["machine"], "x86_64")
            self.assertEqual(info["pe_bits"], 64)
            self.assertEqual(info["image_size"], 0x6000)
            self.assertEqual(info["imports"][0]["dll_normalized"],
                             "kernel32.dll")
            self.assertEqual(info["imports"][0]["symbols"], ["WriteFile"])
            self.assertEqual(info["import_symbol_count"], 1)
            self.assertEqual(info["sections"],
                             [".text", ".data", ".idata", ".pdata", ".xdata"])
            self.assertEqual(make_pe64_abi5_import(), data)


if __name__ == "__main__":
    unittest.main()
