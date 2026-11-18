"""Synthetic Win64 import fixture: structure and import census."""
from pathlib import Path
import hashlib
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe
from scripts.ps5.synthetic_pe64_import import make_pe64_import


class SyntheticPE64ImportTest(unittest.TestCase):
    def test_kernel32_import_and_layout(self):
        data = make_pe64_import()
        self.assertEqual(len(data), 0xE00)
        self.assertEqual(data[0x400:0x404], b"\x48\x83\xEC\x28")
        self.assertEqual(data[0x404:0x40A], b"\xFF\x15\x46\x20\x00\x00")
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "synthetic_import.exe"
            p.write_bytes(data)
            info = inspect_pe(p)
            self.assertEqual(info["machine"], "x86_64")
            self.assertEqual(info["pe_bits"], 64)
            self.assertEqual(info["image_base"], "0x140000000")
            self.assertEqual(info["image_size"], 0x6000)
            self.assertEqual(info["size_of_headers"], 0x400)
            self.assertEqual(
                info["sections"], [".text", ".data", ".idata", ".pdata", ".xdata"])
            self.assertEqual(info["import_dll_count"], 1)
            self.assertEqual(info["import_symbol_count"], 1)
            self.assertEqual(info["imports"][0]["dll_normalized"], "kernel32.dll")
            self.assertEqual(info["imports"][0]["symbols"], ["GetTickCount64"])
            self.assertEqual(info["imports"][0]["runtime_area"], "core")
            self.assertEqual(info["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(make_pe64_import(), data)


if __name__ == "__main__":
    unittest.main()
