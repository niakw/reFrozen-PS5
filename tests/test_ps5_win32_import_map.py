import unittest

from scripts.ps5.map_win32_runtime_imports import classify, parse_nm, safe_object_name


class HostImportMapTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify("SDL_CreateWindow"), "sdl_window_display")
        self.assertEqual(classify("SDL_GetGamepadAxis"), "sdl_gamepad")
        self.assertEqual(classify("SDL_OpenAudioDeviceStream"), "sdl_audio")
        self.assertEqual(classify("SDL_PollEvent"), "sdl_event_input")
        self.assertEqual(classify("SDL_CreateRenderer"), "sdl_renderer_surface")
        self.assertEqual(classify("SDL_GetTicksNS"), "sdl_core_timing")
        self.assertEqual(classify("_ZN6recomp3gfx15CreateGpuDeviceEP10SDL_Window"),
                         "recomp_internal")
        self.assertEqual(classify("_ZNSt3__15mutex4lockEv"), "cxx_runtime")
        self.assertEqual(classify("socket"), "network_posix")
        self.assertEqual(classify("mmap"), "libc_posix_or_other")

    def test_parse_nm(self):
        text = """
                 U SDL_CreateWindow
                 U SDL_CreateWindow
                 U _ZNSt3__15mutex4lockEv
        0000000000000000 T defined_here
        """
        self.assertEqual(parse_nm(text), [
            "SDL_CreateWindow",
            "_ZNSt3__15mutex4lockEv",
        ])

    def test_object_name(self):
        self.assertEqual(safe_object_name("hle/opengl32.cpp"), "hle_opengl32.cpp.o")
        with self.assertRaises(ValueError):
            safe_object_name("../bad.cpp")
        with self.assertRaises(ValueError):
            safe_object_name("/tmp/bad.cpp")


if __name__ == "__main__":
    unittest.main()
