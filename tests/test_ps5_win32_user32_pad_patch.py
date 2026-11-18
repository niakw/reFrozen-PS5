import tempfile
from pathlib import Path
import unittest

from scripts.ps5.patch_x86recomp_runtime_ps5 import patch_win32_user32_pad_events


HEADER = """#pragma once
#include <cstdint>
namespace recomp {
void PumpHostEvents();

}  // namespace recomp
"""

SOURCE = """#include <algorithm>
#include <cstdint>
namespace recomp {
namespace {
int placeholder = 0;
}  // namespace

void PumpHostEvents() {
  (void)placeholder;
}
}  // namespace recomp
"""


class User32PadEventPatchTest(unittest.TestCase):
    def _runtime(self, root: Path) -> Path:
        rt = root / "src/runtime"
        (rt / "hle").mkdir(parents=True)
        (rt / "hle/user32_window.h").write_text(HEADER, encoding="utf-8")
        (rt / "hle/user32_window.cpp").write_text(SOURCE, encoding="utf-8")
        return rt

    def test_injects_public_contract_and_four_handlers(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._runtime(Path(d))
            patch_win32_user32_pad_events(rt)
            header = (rt / "hle/user32_window.h").read_text()
            source = (rt / "hle/user32_window.cpp").read_text()
            for name in (
                "Ps5User32Key",
                "Ps5User32MouseMove",
                "Ps5User32MouseWheel",
                "Ps5User32MouseButton",
            ):
                self.assertEqual(header.count(name), 1)
                self.assertEqual(source.count(f"void {name}"), 1)
            self.assertIn("Post(hwnd, msg, gvk, lp);", source)
            self.assertIn("WM_MOUSEMOVE", source)
            self.assertIn("WM_MOUSEWHEEL", source)
            self.assertIn("SetKey(vk, down);", source)
            self.assertIn("Ps5InputHwnd()", source)

    def test_fails_closed_if_header_anchor_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._runtime(Path(d))
            p = rt / "hle/user32_window.h"
            p.write_text(p.read_text().replace("void PumpHostEvents();\n", ""),
                         encoding="utf-8")
            with self.assertRaises(SystemExit):
                patch_win32_user32_pad_events(rt)

    def test_fails_closed_if_source_anchor_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._runtime(Path(d))
            p = rt / "hle/user32_window.cpp"
            p.write_text(p.read_text().replace("void PumpHostEvents() {",
                                               "void PumpEvents() {"),
                         encoding="utf-8")
            with self.assertRaises(SystemExit):
                patch_win32_user32_pad_events(rt)


if __name__ == "__main__":
    unittest.main()
