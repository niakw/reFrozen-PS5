"""Static safety checks for the preserved PS5 OpenGL SDK fetch recipe."""
from pathlib import Path
import re
import subprocess
import unittest

SCRIPT = Path("scripts/ps5/fetch-verified-opengl-sdk.sh")
EXPECTED_SHA = "30d8e51dd062739b629346102be5932728ba714bc50b1bdcdf08306c8843d9a4"


class OpenGLSdkFetchRecipeTest(unittest.TestCase):
    def test_shell_syntax_and_exact_pin(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        text = SCRIPT.read_text()
        self.assertIn("sdk-v1.0.2/ps5-opengl-sdk-1.0.2.tar.gz", text)
        self.assertIn(EXPECTED_SHA, text)
        self.assertRegex(EXPECTED_SHA, r"^[0-9a-f]{64}$")

    def test_fail_closed_contracts_are_present(self):
        text = SCRIPT.read_text()
        required = [
            "sha256sum --check --strict",
            "unsafe archive member",
            'filter="data"',
            "manifest.sha256",
            "ps5-opengl.mk",
            "libPS5OpenGL.a",
            "include/EGL/egl.h",
            "include/GL/gl.h",
            "THIRD_PARTY_NOTICES.md",
            "REFROZEN_PS5_OPENGL_SDK pass=1",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_does_not_embed_private_or_game_inputs(self):
        text = SCRIPT.read_text().lower()
        for forbidden in ("war3.exe", "game.dll", "blizzard", "wc3fztprv"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
