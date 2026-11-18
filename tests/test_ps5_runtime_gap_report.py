"""Runtime gap reports are tested against synthetic HLE patches and census JSON."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.runtime_gap_report import build_gap_report, reference_hle_surface


class RuntimeGapReportTest(unittest.TestCase):
    def test_reference_unmapped_and_ordinal_statuses(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patches = root / "patches" / "x86recomp"
            patches.mkdir(parents=True)
            (patches / "0001-test.patch").write_text(
                '+HLE("kernel32.dll", VirtualAlloc, 4) { return 0; }\n'
                '+HLE("ws2_32.dll", socket, 3) { return 0; }\n',
                encoding="utf-8",
            )
            census = {
                "results": [{
                    "file": "synthetic.exe",
                    "sha256": "00" * 32,
                    "machine": "x86_64",
                    "pe_bits": 64,
                    "imports": [{
                        "dll": "KERNEL32.dll",
                        "dll_normalized": "kernel32.dll",
                        "runtime_area": "core",
                        "symbols": ["VirtualAlloc", "CreateFileW", "#17"],
                    }],
                }]
            }
            report = build_gap_report(census, root)
            self.assertEqual(report["reference_hle_count"], 2)
            self.assertEqual(report["summary"], {
                "ordinal_needs_manual": 1,
                "reference_hle": 1,
                "unmapped": 1,
            })
            symbols = report["modules"][0]["imports"][0]["symbols"]
            self.assertEqual([x["reference_status"] for x in symbols],
                             ["reference_hle", "unmapped", "ordinal_needs_manual"])
            self.assertTrue(all(x["ps5_status"] == "unverified" for x in symbols))
            self.assertEqual(report["missing_by_dll"], {"kernel32.dll": ["CreateFileW"]})

    def test_hle_regex_ignores_non_handlers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patches = root / "patches" / "x86recomp"
            patches.mkdir(parents=True)
            (patches / "x.patch").write_text(
                'KnownDll("kernel32.dll")\n'
                'HLE("user32.dll", MessageBoxA, 4) {}\n',
                encoding="utf-8",
            )
            self.assertEqual(reference_hle_surface(root),
                             {("user32.dll", "MessageBoxA")})


if __name__ == "__main__":
    unittest.main()
