from pathlib import Path
import tempfile
import unittest

from scripts.ps5.x86recomp_sdl_contract import EXPECTED_UNRESOLVED, GROUPS, scan


class SdlContractTest(unittest.TestCase):
    def test_baseline_is_exactly_partitioned(self):
        union=set()
        for name,symbols in GROUPS.items():
            self.assertTrue(symbols, name)
            self.assertTrue(union.isdisjoint(symbols), name)
            union |= symbols
        self.assertEqual(union, EXPECTED_UNRESOLVED)
        self.assertEqual(len(union), 61)

    def test_scans_calls_and_never_emits_absolute_root(self):
        with tempfile.TemporaryDirectory(prefix="private-runtime-") as d:
            root=Path(d)
            (root/"hle").mkdir()
            (root/"hle"/"window.cpp").write_text(
                "void f(){ SDL_CreateWindow(0,0,0,0); SDL_PollEvent(nullptr); }\n",
                encoding="utf-8",
            )
            (root/"audio.cpp").write_text(
                "void g(){ SDL_OpenAudioDeviceStream(0,0,0,0); SDL_PutAudioStreamData(0,0,0); }\n",
                encoding="utf-8",
            )
            report=scan(root)
            self.assertEqual(report["runtime_sdl_call_count"],4)
            self.assertEqual(
                report["groups"]["window_display_events"]["files"],
                ["hle/window.cpp"],
            )
            self.assertEqual(report["groups"]["audio_stream"]["files"],["audio.cpp"])
            self.assertNotIn(d, str(report))

    def test_extra_sdl_call_is_visible_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"x.cpp").write_text("void x(){ SDL_SomethingNew(); }\n")
            report=scan(root)
            self.assertEqual(
                report["additional_sdl_calls_not_in_55_object_unresolved_baseline"],
                ["SDL_SomethingNew"],
            )


if __name__ == "__main__":
    unittest.main()
