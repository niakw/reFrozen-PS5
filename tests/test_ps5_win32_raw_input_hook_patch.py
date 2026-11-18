import tempfile
from pathlib import Path
import unittest

from scripts.ps5.patch_x86recomp_runtime_ps5 import patch_win32_raw_input_hooks


SOURCE = """#include <cstdint>
namespace recomp {
struct RawInput {
  enum Kind : unsigned char { MouseX, MouseY, Wheel, MouseButton, Key };
};
using RawInputSink = void (*)(const RawInput&);
RawInputSink g_raw_sink = nullptr;
unsigned TickCount() { return 1; }
void EmitRawInput(RawInput::Kind kind, uint8_t code, int32_t value) {
  if (RawInputSink sink = g_raw_sink) sink({kind, code, value, TickCount()});
}

}  // namespace recomp
"""


class Win32RawInputHookPatchTest(unittest.TestCase):
    def _runtime(self, root: Path) -> Path:
        rt = root / "src/runtime"
        (rt / "hle").mkdir(parents=True)
        (rt / "hle/user32_input.cpp").write_text(SOURCE, encoding="utf-8")
        return rt

    def test_adds_four_native_hooks_once(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._runtime(Path(d))
            patch_win32_raw_input_hooks(rt)
            text = (rt / "hle/user32_input.cpp").read_text()
            for name in ("di_key", "di_mouse_move", "di_mouse_wheel",
                         "di_mouse_button"):
                self.assertEqual(text.count(f'extern "C" void {name}'), 1)
            self.assertIn("RawInput::Key", text)
            self.assertIn("RawInput::MouseX", text)
            self.assertIn("RawInput::MouseY", text)
            self.assertIn("RawInput::Wheel", text)
            self.assertIn("RawInput::MouseButton", text)
            self.assertIn("button < 0 || button > 7", text)

    def test_fails_closed_if_upstream_emit_body_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rt = self._runtime(Path(d))
            p = rt / "hle/user32_input.cpp"
            p.write_text(p.read_text().replace("TickCount()", "TickCount64()", 1),
                         encoding="utf-8")
            with self.assertRaises(SystemExit):
                patch_win32_raw_input_hooks(rt)


if __name__ == "__main__":
    unittest.main()
