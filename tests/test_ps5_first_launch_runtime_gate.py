"""First-launch gate tests use sanitized synthetic census data only."""
import unittest

from scripts.ps5.first_launch_runtime_gate import build_gate


def module(imports, markers=None):
    return {
        "file": "classic64.exe",
        "imports": imports,
        "capability_markers": markers or [],
    }


def lib(dll, symbols):
    out = []
    for item in symbols:
        name, status = item[:2]
        units = item[2] if len(item) > 2 else []
        out.append({
            "name": name,
            "reference_status": status,
            "reference_units": units,
        })
    return {"dll": dll, "symbols": out}


class FirstLaunchRuntimeGateTest(unittest.TestCase):
    def test_opengl_wasapi_route_passes_with_compiled_units(self):
        gap = {"modules": [module(
            [
                lib("KERNEL32.dll", [("VirtualAlloc", "reference_win64_hle", ["kernel32.c"])]),
                lib("USER32.dll", [("CreateWindowExW", "reference_win64_hle", ["user32.c"])]),
                lib("OPENGL32.dll", [("wglCreateContext", "reference_win64_hle", ["opengl.m"])]),
                lib("OLE32.dll", [("CoCreateInstance", "reference_win64_hle", ["input.c"])]),
            ],
            [{
                "name": "wasapi_mmdevice_enumerator",
                "area": "audio",
                "count": 1,
                "sections": [".rdata"],
            }],
        )]}
        compiled = {
            name: "PASS" for name in (
                "kernel32.c", "system.c", "handles.c", "files.c",
                "user32.c", "window.c", "display.c", "input.c", "wasapi.c",
            )
        }
        out = build_gate(gap, compiled, {"wgl_egl"})
        self.assertTrue(out["passed"])
        self.assertEqual(out["missing_compile_routes"], [])
        self.assertEqual(out["unresolved_imports"], [])

    def test_xaudio_marker_requires_xaudio_unit(self):
        gap = {"modules": [module(
            [lib("OLE32.dll", [("CoCreateInstance", "reference_win64_hle", ["input.c"])])],
            [{"name": "xaudio2_27", "area": "audio", "count": 1,
              "sections": [".rdata"]}],
        )]}
        out = build_gate(gap, {"input.c": "PASS", "xaudio2.c": "FAIL"}, set())
        self.assertFalse(out["passed"])
        self.assertEqual(out["missing_compile_routes"][0]["requirement"], "xaudio2.c")

    def test_crypto_import_requires_bcrypt_when_observed(self):
        gap = {"modules": [module([
            lib("bcrypt.dll", [("BCryptGenRandom", "reference_win64_hle", ["bcrypt.c"])]),
        ])]}
        out = build_gate(gap, {"bcrypt.c": "FAIL"}, set())
        self.assertFalse(out["passed"])
        self.assertEqual(out["missing_compile_routes"][0]["requirement"], "bcrypt.c")

    def test_unresolved_symbol_fails_even_when_unit_compiles(self):
        gap = {"modules": [module([
            lib("kernel32.dll", [("MissingApi", "unmapped")]),
        ])]}
        compiled = {
            "kernel32.c": "PASS", "system.c": "PASS",
            "handles.c": "PASS", "files.c": "PASS",
        }
        out = build_gate(gap, compiled, set())
        self.assertFalse(out["passed"])
        self.assertEqual(out["unresolved_imports"][0]["symbol"], "MissingApi")

    def test_external_wgl_route_must_be_explicitly_proven(self):
        gap = {"modules": [module([
            lib("opengl32.dll", [("wglSwapBuffers", "reference_win64_hle", ["opengl.m"])]),
        ])]}
        out = build_gate(gap, {}, set())
        self.assertFalse(out["passed"])
        self.assertEqual(
            out["missing_compile_routes"][0]["status"],
            "external_route_unproven",
        )


    def test_unknown_dll_handler_requires_its_actual_source_unit(self):
        gap = {"modules": [module([
            lib("winhttp.dll", [
                ("WinHttpOpen", "reference_win64_hle", ["winhttp.m"]),
            ]),
        ])]}
        out = build_gate(gap, {}, set())
        self.assertFalse(out["passed"])
        self.assertEqual(
            out["missing_compile_routes"][0]["requirement"], "winhttp.m"
        )
        self.assertEqual(
            out["missing_compile_routes"][0]["status"], "not_in_compile_census"
        )
        self.assertEqual(out["unknown_dlls_for_triage"], ["winhttp.dll"])

    def test_reference_handler_without_implementation_unit_fails_closed(self):
        gap = {"modules": [module([
            lib("winhttp.dll", [
                ("WinHttpOpen", "reference_win64_hle", []),
            ]),
        ])]}
        out = build_gate(gap, {}, set())
        self.assertFalse(out["passed"])
        self.assertEqual(
            out["unresolved_imports"][0]["status"],
            "reference_handler_unit_unproven",
        )

    def test_external_route_replaces_original_host_handler_unit(self):
        gap = {"modules": [module([
            lib("opengl32.dll", [
                ("wglCreateContext", "reference_win64_hle", ["opengl.m"]),
            ]),
        ])]}
        out = build_gate(gap, {}, {"wgl_egl"})
        self.assertTrue(out["passed"])
        self.assertNotIn(
            "opengl.m",
            [item["requirement"] for item in out["required"]],
        )


if __name__ == "__main__":
    unittest.main()
