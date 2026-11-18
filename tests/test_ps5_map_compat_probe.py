from pathlib import Path
import hashlib
import struct
import tempfile
import unittest

from scripts.ps5.map_compat_probe import analyze_extracted_map


class MapCompatProbeTest(unittest.TestCase):
    def test_jass_map_is_evidence_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = (
                "function main takes nothing returns nothing\n"
                " call Preload(\"x\")\n"
                " call ExecuteFunc(\"Later\")\n"
                " call BlzSetAbilityTooltip(1, \"x\", 0)\n"
                "endfunction\n"
            ).encode()
            (root / "war3map.j").write_bytes(script)
            (root / "war3map.w3i").write_bytes(
                struct.pack("<III", 25, 7, 6061) + b"fixture"
            )
            report = analyze_extracted_map(root, "ab" * 32)
            self.assertEqual(report["archive_sha256"], "ab" * 32)
            self.assertTrue(report["script_profile"]["has_jass"])
            self.assertFalse(report["script_profile"]["has_lua"])
            self.assertEqual(
                report["script_profile"]["engine_hint"],
                "classic_jass_version_requires_native_census",
            )
            self.assertEqual(
                report["script_profile"]["blz_native_names"],
                ["BlzSetAbilityTooltip"],
            )
            self.assertEqual(report["script_profile"]["markers"]["preload"], 1)
            self.assertEqual(report["script_profile"]["markers"]["execute_func"], 1)
            self.assertTrue(report["w3i_header"]["valid_header"])
            self.assertEqual(report["w3i_header"]["file_format_version"], 25)
            self.assertEqual(report["compatibility"]["status"], "unverified")
            self.assertEqual(
                report["scripts"][0]["sha256"],
                hashlib.sha256(script).hexdigest(),
            )
            self.assertNotIn(str(root), str(report))

    def test_lua_and_native_plugin_are_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "war3map.lua").write_text(
                "function main() BlzFrameSetVisible(nil, true) end\n",
                encoding="utf-8",
            )
            (root / "plugins").mkdir()
            (root / "plugins" / "helper.dll").write_bytes(b"synthetic")
            report = analyze_extracted_map(root)
            self.assertEqual(
                report["script_profile"]["engine_hint"],
                "classic_1_31_or_newer_feature_set",
            )
            self.assertTrue(report["embedded_native_code"]["present"])
            self.assertEqual(report["embedded_native_code"]["count"], 1)
            self.assertEqual(
                report["embedded_native_code"]["relative_files"],
                ["plugins/helper.dll"],
            )
            self.assertEqual(
                report["script_profile"]["blz_native_names"],
                ["BlzFrameSetVisible"],
            )

    def test_short_w3i_fails_advisory_header_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "war3map.j").write_text("function main takes nothing returns nothing\nendfunction\n")
            (root / "war3map.w3i").write_bytes(b"tiny")
            report = analyze_extracted_map(root)
            self.assertFalse(report["w3i_header"]["valid_header"])
            self.assertTrue(report["compatibility"]["requires_runtime_test"])

    def test_missing_directory_fails(self):
        with self.assertRaises(ValueError):
            analyze_extracted_map(Path("/definitely/not/a/map"))


if __name__ == "__main__":
    unittest.main()
