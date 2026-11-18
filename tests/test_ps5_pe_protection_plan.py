"""PS5 PE protection planning tests use only synthetic images."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe
from scripts.ps5.pe_protection_plan import plan_module, ProtectionPlanError
from scripts.ps5.synthetic_pe64_memory import make_pe64_memory


class ProtectionPlanTest(unittest.TestCase):
    def test_16k_granules_never_map_guest_text_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "memory.exe"
            p.write_bytes(make_pe64_memory())
            module = inspect_pe(p)
            plan = plan_module(module)
            self.assertEqual(plan["granule"], 0x4000)
            self.assertTrue(plan["requires_guest_4k_protection_model_for_exact_windows_semantics"])
            self.assertEqual(plan["coarse_write_broadening_granules"],
                             ["0x140000000"])
            self.assertEqual(plan["guest_executable_byte_granules"],
                             ["0x140000000"])
            self.assertEqual(plan["segments"], [
                {
                    "start": "0x140000000",
                    "end": "0x140004000",
                    "granules": 1,
                    "host_protection": "rw-",
                    "host_execute": False,
                    "coarse_write_broadening": True,
                    "contains_guest_executable_bytes": True,
                },
                {
                    "start": "0x140004000",
                    "end": "0x140008000",
                    "granules": 1,
                    "host_protection": "r--",
                    "host_execute": False,
                    "coarse_write_broadening": False,
                    "contains_guest_executable_bytes": False,
                },
            ])
            self.assertTrue(all(not s["host_execute"] for s in plan["segments"]))

    def test_clean_16k_section_boundaries_need_no_write_broadening(self):
        module = {
            "file": "aligned.dll",
            "image_base": "0x180000000",
            "image_size": 0xC000,
            "size_of_headers": 0x4000,
            "section_details": [
                {"name": ".text", "virtual_address": 0x4000,
                 "virtual_size": 0x4000, "raw_size": 0x4000,
                 "read": True, "write": False, "execute": True},
                {"name": ".data", "virtual_address": 0x8000,
                 "virtual_size": 0x4000, "raw_size": 0x4000,
                 "read": True, "write": True, "execute": False},
            ],
        }
        plan = plan_module(module)
        self.assertEqual(plan["coarse_write_broadening_granules"], [])
        self.assertFalse(plan["requires_guest_4k_protection_model_for_exact_windows_semantics"])
        self.assertEqual([s["host_protection"] for s in plan["segments"]],
                         ["r--", "rw-"])

    def test_out_of_image_section_fails_closed(self):
        module = {
            "file": "bad.exe",
            "image_base": "0x140000000",
            "image_size": 0x4000,
            "size_of_headers": 0x400,
            "section_details": [
                {"name": ".bad", "virtual_address": 0x3000,
                 "virtual_size": 0x4000, "raw_size": 0x4000,
                 "read": True, "write": False, "execute": False},
            ],
        }
        with self.assertRaises(ProtectionPlanError):
            plan_module(module)


if __name__ == "__main__":
    unittest.main()
