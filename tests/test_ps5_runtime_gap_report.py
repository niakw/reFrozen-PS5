"""Runtime gap reports are tested against synthetic HLE patches and census JSON."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.runtime_gap_report import (
    build_gap_report, reference_hle_surface, reference_win64_surface,
)


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
                    "machine": "x86",
                    "pe_bits": 32,
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
            self.assertFalse(report["reference_surface"]["complete"])
            self.assertEqual(report["reference_surface"]["mode"], "patch_delta_only")
            self.assertEqual(report["summary"], {
                "ordinal_needs_manual": 1,
                "reference_hle": 1,
                "unmapped": 1,
            })
            symbols = report["modules"][0]["imports"][0]["symbols"]
            self.assertEqual([x["reference_status"] for x in symbols],
                             ["reference_hle", "unmapped", "ordinal_needs_manual"])
            self.assertTrue(all(x["ps5_status"] == "unverified" for x in symbols))
            self.assertTrue(all("resolved_name" in x for x in symbols))
            self.assertEqual(report["missing_by_dll"], {"kernel32.dll": ["CreateFileW"]})


    def test_win64_surface_is_architecture_specific_and_path_private(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            patches = root / "patches" / "x86recomp"
            patches.mkdir(parents=True)
            (patches / "x.patch").write_text(
                '+HLE("kernel32.dll", CreateFileW, 7) { return 0; }\n',
                encoding="utf-8",
            )
            win64 = Path(temp) / "external-win64-runtime"
            win64.mkdir()
            (win64 / "kernel32.c").write_text(
                "void I_kernel32_dll_VirtualAlloc(CPU *c) {}\n"
                "void I_kernel32_dll_CreateThread(CPU *c) {}\n",
                encoding="utf-8",
            )
            census = {
                "results": [{
                    "file": "classic64.exe",
                    "machine": "x86_64",
                    "pe_bits": 64,
                    "imports": [{
                        "dll": "KERNEL32.dll",
                        "dll_normalized": "kernel32.dll",
                        "runtime_area": "core",
                        "symbols": ["VirtualAlloc", "CreateFileW", "MissingApi"],
                    }],
                }]
            }
            report = build_gap_report(census, root, win64)
            self.assertEqual(
                report["modules"][0]["target_runtime"], "win64_candidate")
            symbols = report["modules"][0]["imports"][0]["symbols"]
            self.assertEqual(
                [x["reference_status"] for x in symbols],
                ["reference_win64_hle", "reference_other_arch", "unmapped"],
            )
            self.assertEqual(
                report["missing_by_dll"],
                {"kernel32.dll": ["CreateFileW", "MissingApi"]},
            )
            self.assertEqual(
                report["reference_surfaces"]["win64_candidate"]["handler_count"], 2)
            self.assertTrue(
                report["reference_surfaces"]["win64_candidate"]["complete"])
            self.assertIsNone(
                report["reference_surfaces"]["win64_candidate"]["root_recorded"])
            self.assertNotIn(str(win64), str(report))
            self.assertEqual(
                reference_win64_surface(win64),
                {("kernel32.dll", "VirtualAlloc"),
                 ("kernel32.dll", "CreateThread")},
            )

    def test_local_guest_dll_resolves_named_and_ordinal_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "patches" / "x86recomp").mkdir(parents=True)
            census = {
                "results": [
                    {
                        "file": "war3.exe",
                        "machine": "x86",
                        "pe_bits": 32,
                        "imports": [{
                            "dll": "Storm.dll",
                            "dll_normalized": "storm.dll",
                            "runtime_area": "unknown",
                            "symbols": ["StormOpenFile", "#17"],
                        }],
                    },
                    {
                        "file": "Storm.dll",
                        "machine": "x86",
                        "pe_bits": 32,
                        "imports": [],
                        "exports": [
                            {"name": "StormOpenFile", "ordinal": 5,
                             "rva": "0x1000", "forwarder": None},
                            {"name": "StormOrdinal17", "ordinal": 17,
                             "rva": "0x2000", "forwarder": None},
                        ],
                    },
                ]
            }
            report = build_gap_report(census, root)
            symbols = report["modules"][0]["imports"][0]["symbols"]
            self.assertEqual(symbols[0]["reference_status"], "local_module")
            self.assertIsNone(symbols[0]["resolved_name"])
            self.assertEqual(symbols[1]["reference_status"], "local_module_ordinal")
            self.assertEqual(symbols[1]["resolved_name"], "StormOrdinal17")
            self.assertEqual(report["summary"],
                             {"local_module": 1, "local_module_ordinal": 1})

    def test_capability_markers_are_carried_without_local_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "patches" / "x86recomp").mkdir(parents=True)
            census = {
                "results": [{
                    "file": "classic64.exe",
                    "sha256": "12" * 32,
                    "machine": "x86_64",
                    "pe_bits": 64,
                    "imports": [{
                        "dll": "bcrypt.dll",
                        "dll_normalized": "bcrypt.dll",
                        "runtime_area": "crypto",
                        "symbols": ["BCryptGenRandom"],
                    }],
                    "com_guid_markers": [{
                        "name": "xaudio2_27",
                        "area": "audio",
                        "guid": "5A508685-A254-4FBA-9B82-9A24B00306AF",
                        "count": 1,
                        "sections": [".rdata"],
                    }],
                }]
            }
            report = build_gap_report(census, root)
            module = report["modules"][0]
            self.assertEqual(report["schema"], 3)
            self.assertEqual(module["imports"][0]["runtime_area"], "crypto")
            self.assertEqual(module["capability_markers"][0]["name"], "xaudio2_27")
            self.assertNotIn(str(Path(temp)), str(report))

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
