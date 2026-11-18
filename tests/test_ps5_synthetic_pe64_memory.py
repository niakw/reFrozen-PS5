"""Validate the synthetic Win64 identity-memory PE layout."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe
from scripts.ps5.synthetic_pe64_memory import make_pe64_memory


class SyntheticPE64MemoryTest(unittest.TestCase):
    def test_layout_and_preferred_addresses(self):
        data = make_pe64_memory()
        self.assertEqual(len(data), 0xC00)
        self.assertEqual(data[0x600:0x604], (41).to_bytes(4, "little"))
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "memory.exe"
            p.write_bytes(data)
            info = inspect_pe(p)
            self.assertEqual(info["machine"], "x86_64")
            self.assertEqual(info["image_base"], "0x140000000")
            self.assertEqual(info["image_size"], 0x5000)
            self.assertEqual(info["sections"],
                             [".text", ".data", ".pdata", ".xdata"])
            self.assertEqual(info["imports"], [])


if __name__ == "__main__":
    unittest.main()
