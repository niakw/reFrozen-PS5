"""Host-only safety and reporting tests. No Warcraft binaries are required."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.ps5_portability_inventory import inventory


class InventoryTest(unittest.TestCase):
    def test_classifies_sample_and_reports_line_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            (root / "src" / "sample.cpp").write_text(
                '#include <dlfcn.h>\n'
                'auto x = dlopen("game.dylib", RTLD_NOW);\n'
                'SDL_GL_CreateContext(window);\n',
                encoding="utf-8",
            )
            report = inventory(root)
            self.assertEqual(report["schema"], 1)
            self.assertEqual(report["counts"]["unix_dynamic_loading"], 1)
            self.assertEqual(report["counts"]["graphics"], 1)
            self.assertGreaterEqual(report["counts"]["apple_platform"], 1)
            self.assertEqual([x["line"] for x in report["findings"]], [2, 3])
            json.dumps(report)

    def test_no_game_data_and_missing_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "game").mkdir()
            (root / "game" / "Game.dll").write_bytes(b"SDL_GL_")
            report = inventory(root)
            self.assertEqual(report["findings"], [])
            self.assertTrue(all(value == 0 for value in report["counts"].values()))


if __name__ == "__main__":
    unittest.main()
