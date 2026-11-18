import unittest

from scripts.ps5.private_build_plan import build_plan


def census(bits=64, machine="x86_64", storage="casc", route="opengl_wgl_to_ps5_egl"):
    return {
        "storage_layout": {"classification": storage},
        "results": [{
            "file": "Warcraft III.exe",
            "relative_file": "x86_64/Warcraft III.exe",
            "sha256": "a" * 64,
            "machine": machine,
            "pe_bits": bits,
            "version_resource": {"file_version": "1.31.1.12164"},
            "graphics_profile": {
                "ps5_initial_route": route,
                "static_backends": [{"backend": "opengl", "dlls": ["opengl32.dll"]}]
                if route == "opengl_wgl_to_ps5_egl" else [],
            },
        }],
    }


def gate(passed=True, external=("wgl_egl",)):
    return {
        "passed": passed,
        "missing_compile_routes": [] if passed else [{"requirement": "kernel32.c"}],
        "unresolved_imports": [],
        "external_routes_proven": list(external),
    }


def receipt(passed=True):
    return {
        "probe": "PPSA99006",
        "marker": "REFROZEN_PS5_WGL_TITLE",
        "pass": 1 if passed else 0,
        "eboot_sha256": "b" * 64,
    }


class PrivateBuildPlanTest(unittest.TestCase):
    def test_win64_ready_path(self):
        plan = build_plan(census(), gate(), receipt())
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(plan["lifter"]["id"], "nightsight_recomp64")
        self.assertEqual(plan["renderer"]["route"], "wgl_egl")
        self.assertEqual(plan["content"]["route"], "casc_reader")
        self.assertEqual(plan["entry"]["sha256"], "a" * 64)
        self.assertEqual(plan["blockers"], [])

    def test_win32_uses_refrozen_lifter(self):
        plan = build_plan(
            census(bits=32, machine="x86", storage="legacy_mpq"),
            gate(), receipt(),
        )
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(plan["lifter"]["id"], "refrozen_x86recomp")
        self.assertEqual(plan["content"]["route"], "legacy_mpq_reader")

    def test_missing_hardware_receipt_blocks(self):
        plan = build_plan(census(), gate(), None)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("PPSA99006" in item for item in plan["blockers"]))

    def test_unproven_renderer_blocks(self):
        plan = build_plan(
            census(route="renderer_translation_or_runtime_forcing_required"),
            gate(external=()), receipt(),
        )
        self.assertEqual(plan["status"], "blocked")
        self.assertIsNone(plan["renderer"]["route"])

    def test_wgl_route_must_be_recorded_by_runtime_gate(self):
        plan = build_plan(census(), gate(external=()), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertIn(
            "runtime gate did not record the wgl_egl external route",
            plan["blockers"],
        )

    def test_runtime_failure_blocks(self):
        plan = build_plan(census(), gate(False), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("first-launch runtime gate is not PASS", plan["blockers"])

    def test_partial_content_layout_blocks(self):
        plan = build_plan(census(storage="partial_or_unrecognized"), gate(), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("content layout" in item for item in plan["blockers"]))

    def test_multiple_unknown_exes_require_entry_selection(self):
        c = census()
        c["results"][0]["file"] = "Launcher.exe"
        c["results"].append({
            **c["results"][0],
            "file": "Other.exe",
            "relative_file": "Other.exe",
            "sha256": "c" * 64,
        })
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertIsNone(plan["entry"])
        selected = build_plan(c, gate(), receipt(), entry_name="Other.exe")
        self.assertEqual(selected["entry"]["file"], "Other.exe")

    def test_map_summary_is_advisory(self):
        maps = [
            {
                "script_profile": {
                    "has_jass": True, "has_lua": False,
                    "engine_hint": "classic_jass_version_requires_native_census",
                },
                "embedded_native_code": {"present": False},
            },
            {
                "script_profile": {
                    "has_jass": False, "has_lua": True,
                    "engine_hint": "classic_1_31_or_newer_feature_set",
                },
                "embedded_native_code": {"present": True},
            },
        ]
        plan = build_plan(census(), gate(), receipt(), map_reports=maps)
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(plan["maps"]["reports"], 2)
        self.assertEqual(plan["maps"]["script_languages"], {"jass": 1, "lua": 1})
        self.assertEqual(plan["maps"]["embedded_native_code_warnings"], 1)


if __name__ == "__main__":
    unittest.main()
