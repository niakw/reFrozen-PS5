"""Public synthetic census tests: no Blizzard code or files."""
import tempfile
from pathlib import Path
import unittest

from scripts.ps5.verify_refrozen_126a_input import (
    EXPECTED_CORE_SHA256,
    GAME_ASSETS,
    LIFTER_MODULES,
    asset_status,
    validate,
)


def mock_census():
    results = []
    for path in LIFTER_MODULES:
        e = {
            "file": path.rsplit("/", 1)[-1],
            "relative_file": path,
            "pe_bits": 32,
            "machine": "x86",
            "sha256": EXPECTED_CORE_SHA256.get(path, "1" * 64),
            "version_resource": {"file_version": "1.26.0.6401"},
        }
        results.append(e)
    # A duplicate filename in an optional community plug-in folder is not
    # the same binary as the one the upstream lift.sh uses.
    results.append({
        "file": "Storm.dll", "relative_file": "ICCup/Storm.dll",
        "pe_bits": 32, "machine": "x86", "sha256": "0" * 64
    })
    return {"results": results}


class InputGateTest(unittest.TestCase):
    def test_exact_four_hashes_and_eleven_modules(self):
        result = validate(mock_census())
        self.assertTrue(result["ready_for_lifter"])
        self.assertFalse(result["ready_for_game_launch"])
        self.assertEqual(result["modules_required"], 11)
        self.assertEqual(result["modules_present"], 11)
        self.assertEqual(len(result["core_hashes_matching"]), 4)
        self.assertEqual(result["failures"], [])
        self.assertTrue(all(x == "not_checked" for x in result["asset_status"].values()))

    def test_wrong_hash_fails_closed(self):
        census = mock_census()
        census["results"][1]["sha256"] = "0" * 64
        result = validate(census)
        self.assertFalse(result["ready_for_lifter"])
        self.assertEqual(result["failures"][0]["module"], "game.dll")
        self.assertEqual(result["failures"][0]["reason"], "sha256_not_matching_upstream_126a")

    def test_wrong_version_and_wrong_architecture(self):
        census = mock_census()
        census["results"][0]["version_resource"] = {"file_version": "1.31.1.12164"}
        census["results"][2]["pe_bits"] = 64
        result = validate(census)
        self.assertFalse(result["ready_for_lifter"])
        self.assertIn("file_version_not_126a_6401", [x["reason"] for x in result["failures"]])
        self.assertIn("not_pe32_x86", [x["reason"] for x in result["failures"]])

    def test_missing_and_duplicate_module(self):
        census = mock_census()
        census["results"].pop(5)
        self.assertFalse(validate(census)["ready_for_lifter"])
        census = mock_census()
        census["results"].append(dict(census["results"][0]))
        result = validate(census)
        self.assertFalse(result["ready_for_lifter"])
        self.assertIn("duplicate", [x["reason"] for x in result["failures"]])

    def test_lfs_pointers_block_launch_only(self):
        census = mock_census()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in GAME_ASSETS:
                (root / name).write_bytes(b"MPQ\x1a" + b"\x00" * 1024)
            result = validate(census, root)
            self.assertTrue(result["ready_for_game_launch"])
            (root / "war3x.mpq").unlink()
            (root / "war3x.mpq").write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:" + b"a" * 64 + b"\nsize 1234\n"
            )
            result = validate(census, root)
            self.assertTrue(result["ready_for_lifter"])
            self.assertFalse(result["ready_for_game_launch"])
            self.assertEqual(result["asset_status"]["war3x.mpq"], "lfs_pointer_only")
            self.assertEqual(asset_status(root)["war3.mpq"], "materialized_unverified")

    def test_only_metadata_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="secret-install-location-") as d:
            result = validate(mock_census(), Path(d))
            self.assertNotIn(d, str(result))
            self.assertNotIn("private", str(result))


if __name__ == "__main__":
    unittest.main()
