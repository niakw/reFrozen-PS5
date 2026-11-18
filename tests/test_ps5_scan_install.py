"""Directory scanner tests use synthetic PE fixtures only."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.scan_install import scan_install
from scripts.ps5.synthetic_pe64 import make_pe64


class InstallScannerTest(unittest.TestCase):
    def test_scans_pe_candidates_without_absolute_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "redist" / "miles").mkdir(parents=True)
            (root / "Warcraft III.exe").write_bytes(make_pe64())
            (root / "redist" / "miles" / "codec.asi").write_bytes(make_pe64())
            (root / "not-a-module.txt").write_text("ignore", encoding="utf-8")
            (root / "broken.dll").write_bytes(b"not a PE")
            report = scan_install(root)
            self.assertIsNone(report["root"])
            self.assertEqual(report["module_count"], 2)
            self.assertEqual(report["skipped_candidate_count"], 1)
            rels = {x["relative_file"] for x in report["results"]}
            self.assertEqual(rels, {"Warcraft III.exe", "redist/miles/codec.asi"})
            self.assertEqual(report["skipped_candidates"][0]["relative_file"], "broken.dll")
            self.assertNotIn(str(root), str(report))


    def test_detects_casc_layout_without_enumerating_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Data" / "data").mkdir(parents=True)
            (root / "Data" / "indices").mkdir()
            (root / "Data" / "config").mkdir()
            (root / ".build.info").write_text("synthetic", encoding="utf-8")
            (root / "Data" / "data" / "0000000000.idx").write_bytes(b"fixture")
            report = scan_install(root)
            self.assertEqual(report["storage_layout"]["classification"], "casc")
            self.assertTrue(report["storage_layout"]["casc_markers"]["data_data"])
            self.assertTrue(report["storage_layout"]["casc_markers"]["data_indices"])
            self.assertTrue(report["storage_layout"]["casc_markers"]["build_info"])
            self.assertNotIn("0000000000.idx", str(report))

    def test_detects_legacy_mpq_and_mixed_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "War3.mpq").write_bytes(b"fixture")
            (root / "War3x.mpq").write_bytes(b"fixture")
            report = scan_install(root)
            self.assertEqual(report["storage_layout"]["classification"], "legacy_mpq")
            self.assertEqual(
                report["storage_layout"]["legacy_mpq_markers"],
                ["war3.mpq", "war3x.mpq"],
            )

            (root / "DATA" / "DATA").mkdir(parents=True)
            (root / "DATA" / "INDICES").mkdir()
            mixed = scan_install(root)
            self.assertEqual(
                mixed["storage_layout"]["classification"],
                "mixed_casc_and_legacy_mpq",
            )

    def test_partial_storage_layout_does_not_overclaim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Data").mkdir()
            report = scan_install(root)
            self.assertEqual(
                report["storage_layout"]["classification"],
                "partial_or_unrecognized",
            )

    def test_missing_directory_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            with self.assertRaises(ValueError):
                scan_install(missing)


if __name__ == "__main__":
    unittest.main()
