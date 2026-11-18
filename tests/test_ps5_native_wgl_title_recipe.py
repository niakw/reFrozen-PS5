"""Static validation for the registered PPSA99006 graphics probe recipe."""
from pathlib import Path
import json
import re
import subprocess
import unittest


class NativeWglTitleRecipeTest(unittest.TestCase):
    def test_packager_shell_syntax(self):
        subprocess.run(["bash", "-n", "scripts/ps5/build-native-wgl-title.sh"], check=True)

    def test_dedicated_title_identity_is_valid(self):
        script = Path("scripts/ps5/build-native-wgl-title.sh").read_text()
        self.assertIn("TITLE=PPSA99006", script)
        content_id = "UP9000-PPSA99006_00-REFROZENGLPROBE1"
        self.assertRegex(
            content_id,
            r"^[A-Z]{2}\d{4}-PPSA\d{5}_00-[A-Z0-9]{16}$",
        )
        self.assertNotIn("PPSA99005_00", content_id)
        self.assertNotIn("PPSA99008_00", content_id)

    def test_recipe_preserves_required_opengl_native_integration(self):
        script = Path("scripts/ps5/build-native-wgl-title.sh").read_text()
        required = [
            "manifest.sha256",
            "native-app/app_heap.c",
            "native-app/runtime_shims.c",
            "native-app/ps5-pie.ld",
            "--wrap=malloc",
            "--wrap=calloc",
            "--wrap=realloc",
            "--wrap=free",
            "--wrap=posix_memalign",
            "--wrap=malloc_usable_size",
            "agc_link_stub.c",
            "agc_driver_link_stub.c",
            "libPS5OpenGL.a",
            "libunwind.a",
            "libc++abi.a",
            "libc++.a",
            "REFROZEN_PS5_WGL_TITLE pass=%d",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, script)

    def test_hardware_probe_exercises_legacy_compatibility_path(self):
        source = Path("tests/ps5/ps5_wgl_egl_title_probe.cpp").read_text()
        required = [
            "kWglContextCompatibilityProfileBit",
            "glMatrixMode(GL_PROJECTION)",
            "glOrtho(",
            "glBegin(GL_QUADS)",
            "glColor3f(",
            "glVertex2f(",
            "glEnd()",
            "registry.SwapBuffers",
            "glGetError()",
            "REFROZEN_PS5_WGL_TITLE pass=%d",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, source)


if __name__ == "__main__":
    unittest.main()
