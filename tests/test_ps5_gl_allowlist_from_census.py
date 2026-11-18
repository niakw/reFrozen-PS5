"""Tests for static OpenGL allowlist derivation from private-census shape."""
import unittest

from scripts.ps5.gl_allowlist_from_census import (
    CensusError,
    derive_static_gl_surface,
    render_allowlist,
)


class GlAllowlistFromCensusTest(unittest.TestCase):
    def test_deduplicates_gl_and_excludes_wgl(self):
        census = {
            "results": [
                {
                    "file": "Warcraft III.exe",
                    "relative_file": "x86_64/Warcraft III.exe",
                    "imports": [
                        {
                            "dll": "OPENGL32.dll",
                            "dll_normalized": "opengl32.dll",
                            "symbols": [
                                "glClear", "glViewport",
                                "wglCreateContext", "wglGetProcAddress",
                            ],
                        },
                        {
                            "dll": "KERNEL32.dll",
                            "dll_normalized": "kernel32.dll",
                            "symbols": ["CreateFileW"],
                        },
                    ],
                },
                {
                    "file": "Game.dll",
                    "imports": [
                        {
                            "dll_normalized": "opengl32.dll",
                            "symbols": ["glClear", "glBindTexture", "#7"],
                        }
                    ],
                },
            ]
        }
        report = derive_static_gl_surface(census)
        self.assertEqual(
            report["static_gl_functions"],
            ["glBindTexture", "glClear", "glViewport"],
        )
        self.assertEqual(report["function_count"], 3)
        self.assertEqual(
            report["modules_with_opengl"],
            ["Game.dll", "Warcraft III.exe"],
        )
        self.assertEqual(
            report["provenance"]["glClear"],
            ["Game.dll", "Warcraft III.exe"],
        )
        self.assertEqual(
            report["ordinal_imports"],
            [{"module": "Game.dll", "symbol": "#7"}],
        )
        self.assertNotIn("wglCreateContext", render_allowlist(report))
        self.assertIn("\nglClear\n", render_allowlist(report))
        self.assertEqual(report["dynamic_proc_surface"], "not_observed")

    def test_skips_failed_module_and_no_opengl(self):
        report = derive_static_gl_surface({
            "results": [
                {"file": "bad.dll", "error": "broken"},
                {
                    "file": "audio.dll",
                    "imports": [{
                        "dll_normalized": "winmm.dll",
                        "symbols": ["timeGetTime"],
                    }],
                },
            ]
        })
        self.assertEqual(report["function_count"], 0)
        self.assertEqual(report["modules_with_opengl"], [])
        self.assertEqual(report["ordinal_imports"], [])

    def test_rejects_unexpected_opengl_name(self):
        with self.assertRaisesRegex(CensusError, "unexpected"):
            derive_static_gl_surface({
                "results": [{
                    "file": "bad.exe",
                    "imports": [{
                        "dll_normalized": "opengl32.dll",
                        "symbols": ["NotActuallyGL"],
                    }],
                }]
            })

    def test_rejects_bad_shape(self):
        with self.assertRaisesRegex(CensusError, "results"):
            derive_static_gl_surface({})
        with self.assertRaisesRegex(CensusError, "imports"):
            derive_static_gl_surface({"results": [{"file": "x.exe", "imports": {}}]})


if __name__ == "__main__":
    unittest.main()
