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

    def test_verified_console_receipt_shape_is_accepted(self):
        real = {
            "schema": 1,
            "passed": True,
            "version": "4.6 (Compatibility Profile) Mesa PS5",
            "renderer": "PS5 OpenGL Driver",
            "width": 1920,
            "height": 1080,
            "frames": 120,
            "clear": True,
            "delete": True,
            "receipt_count": 1,
            "terminal_line": (
                "REFROZEN_PS5_WGL_TITLE pass=1 "
                "version=4.6 (Compatibility Profile) Mesa PS5 "
                "renderer=PS5 OpenGL Driver width=1920 height=1080 "
                "frames=120 clear=1 delete=1"
            ),
            "eboot_sha256": "B" * 64,
        }
        plan = build_plan(census(), gate(), real)
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertTrue(plan["graphics_hardware"]["qualified"])
        self.assertEqual(
            plan["graphics_hardware"]["receipt"]["eboot_sha256"], "b" * 64
        )

    def test_console_receipt_semantics_fail_closed(self):
        bad = {
            "passed": True,
            "width": 1920,
            "height": 1080,
            "frames": 119,
            "clear": True,
            "delete": True,
            "terminal_line": (
                "REFROZEN_PS5_WGL_TITLE pass=1 version=4.6 "
                "renderer=PS5 width=1920 height=1080 frames=119 clear=1 delete=1"
            ),
            "eboot_sha256": "c" * 64,
        }
        plan = build_plan(census(), gate(), bad)
        self.assertEqual(plan["status"], "blocked")
        self.assertFalse(plan["graphics_hardware"]["qualified"])

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

    def test_recursive_local_module_closure(self):
        c = census()
        c["results"][0]["imports"] = [{
            "dll": "Game.dll", "dll_normalized": "game.dll",
            "symbols": ["GameMain"], "count": 1,
        }]
        c["results"] += [
            {
                "file": "Game.dll",
                "relative_file": "x86_64/Game.dll",
                "sha256": "c" * 64,
                "machine": "x86_64",
                "pe_bits": 64,
                "image_base": "0x180000000",
                "image_size": 0x500000,
                "imports": [{
                    "dll": "Storm.dll", "dll_normalized": "storm.dll",
                    "symbols": ["SFileOpenArchive"], "count": 1,
                }],
            },
            {
                "file": "Storm.dll",
                "relative_file": "x86_64/Storm.dll",
                "sha256": "d" * 64,
                "machine": "x86_64",
                "pe_bits": 64,
                "image_base": "0x190000000",
                "image_size": 0x200000,
                "imports": [{
                    "dll": "kernel32.dll", "dll_normalized": "kernel32.dll",
                    "symbols": ["CreateFileW"], "count": 1,
                }],
            },
        ]
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(
            [module["relative_file"] for module in plan["local_modules"]],
            ["x86_64/Game.dll", "x86_64/Storm.dll"],
        )
        self.assertEqual(plan["local_modules"][0]["sha256"], "c" * 64)

    def test_local_module_same_directory_wins(self):
        c = census()
        c["results"][0]["imports"] = [{
            "dll": "Game.dll", "dll_normalized": "game.dll",
            "symbols": ["GameMain"], "count": 1,
        }]
        base = {
            "file": "Game.dll",
            "sha256": "c" * 64,
            "machine": "x86_64",
            "pe_bits": 64,
            "image_base": "0x180000000",
            "image_size": 0x100000,
            "imports": [],
        }
        c["results"].append({**base, "relative_file": "x86_64/Game.dll"})
        c["results"].append({
            **base, "relative_file": "plugins/Game.dll", "sha256": "d" * 64,
        })
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(
            [module["relative_file"] for module in plan["local_modules"]],
            ["x86_64/Game.dll"],
        )

    def test_ambiguous_local_module_blocks(self):
        c = census()
        c["results"][0]["imports"] = [{
            "dll": "Plugin.dll", "dll_normalized": "plugin.dll",
            "symbols": ["Start"], "count": 1,
        }]
        for directory, sha in (("plugins/a", "c"), ("plugins/b", "d")):
            c["results"].append({
                "file": "Plugin.dll",
                "relative_file": f"{directory}/Plugin.dll",
                "sha256": sha * 64,
                "machine": "x86_64",
                "pe_bits": 64,
                "image_base": "0x180000000",
                "image_size": 0x100000,
                "imports": [],
            })
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("ambiguous local module" in b for b in plan["blockers"]))

    def test_local_module_architecture_mismatch_blocks(self):
        c = census()
        c["results"][0]["imports"] = [{
            "dll": "Legacy.dll", "dll_normalized": "legacy.dll",
            "symbols": ["Start"], "count": 1,
        }]
        c["results"].append({
            "file": "Legacy.dll",
            "relative_file": "x86_64/Legacy.dll",
            "sha256": "e" * 64,
            "machine": "x86",
            "pe_bits": 32,
            "image_base": "0x10000000",
            "image_size": 0x100000,
            "imports": [],
        })
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("architecture mismatch" in b for b in plan["blockers"]))

    def test_nonlocal_system_import_does_not_create_module(self):
        c = census()
        c["results"][0]["imports"] = [{
            "dll": "kernel32.dll", "dll_normalized": "kernel32.dll",
            "symbols": ["CreateFileW"], "count": 1,
        }]
        plan = build_plan(c, gate(), receipt())
        self.assertEqual(plan["status"], "ready_for_private_lift_and_link")
        self.assertEqual(plan["local_modules"], [])

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
