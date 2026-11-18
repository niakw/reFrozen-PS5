import tempfile
from pathlib import Path
import unittest

from scripts.ps5.patch_x86recomp_runtime_ps5 import patch_monotonic_timing


class MonotonicTimingPatchTest(unittest.TestCase):
    def _tree(self, root: Path) -> Path:
        rt = root / "src" / "runtime"
        (rt / "hle").mkdir(parents=True)
        samples = {
            "ddraw.cpp": '#include "runtime/log.h"\n'
                         'auto a = SDL_GetTicks();\n'
                         'auto b = SDL_GetTicks();\n',
            "present.cpp": '#include "runtime/log.h"\n'
                           'auto a = SDL_GetTicksNS();\n'
                           'auto b = SDL_GetTicksNS();\n',
            "user32_window.cpp": '#include "runtime/log.h"\n' +
                                 ''.join(
                                     f'auto t{i} = SDL_GetTicks();\n'
                                     for i in range(6)
                                 ),
        }
        for name, text in samples.items():
            (rt / "hle" / name).write_text(text, encoding="utf-8")
        return rt

    def test_exact_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._tree(Path(d))
            patch_monotonic_timing(rt)
            ddraw = (rt / "hle/ddraw.cpp").read_text()
            present = (rt / "hle/present.cpp").read_text()
            window = (rt / "hle/user32_window.cpp").read_text()
            all_text = ddraw + present + window
            self.assertNotIn("SDL_GetTicks()", all_text)
            self.assertNotIn("SDL_GetTicksNS()", all_text)
            self.assertEqual(all_text.count('#include "runtime/platform.h"'), 3)
            self.assertEqual(
                all_text.count("(platform::MonotonicNs() / 1000000ULL)"), 8
            )
            self.assertEqual(all_text.count("platform::MonotonicNs()"), 10)

    def test_fails_closed_if_upstream_call_count_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._tree(Path(d))
            p = rt / "hle/user32_window.cpp"
            p.write_text(
                p.read_text().replace("auto t5 = SDL_GetTicks();\n", ""),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                patch_monotonic_timing(rt)

    def test_fails_closed_if_include_anchor_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._tree(Path(d))
            p = rt / "hle/ddraw.cpp"
            p.write_text(p.read_text().replace('#include "runtime/log.h"\n', ""))
            with self.assertRaises(SystemExit):
                patch_monotonic_timing(rt)


if __name__ == "__main__":
    unittest.main()
