import unittest

from scripts.ps5.generate_private_game_config import (
    GameConfigError,
    render_game_config,
)


def ready(exe="Warcraft III.exe", sha="a" * 64):
    return {
        "status": "ready_for_private_lift_and_link",
        "entry": {
            "file": exe,
            "sha256": sha,
            "machine": "x86_64",
            "pe_bits": 64,
        },
    }


class GeneratePrivateGameConfigTest(unittest.TestCase):
    def test_ready_plan_generates_offline_ps5_config(self):
        source = render_game_config(ready())
        self.assertIn('.name = "Warcraft III Classic"', source)
        self.assertIn('.exe = "Warcraft III.exe"', source)
        self.assertIn('.steam_app_id = 0', source)
        self.assertIn('.computer_name = "PS5"', source)
        self.assertIn('.extra_args = NULL', source)
        self.assertIn("a" * 64, source)
        self.assertNotIn("/Users/", source)
        self.assertNotIn("/home/", source)

    def test_relaunch_prefix_tracks_entry_stem(self):
        source = render_game_config(ready("Frozen Throne.exe"))
        self.assertIn('.relaunch_prefix = "Frozen Throne"', source)

    def test_blocked_plan_rejected(self):
        plan = ready()
        plan["status"] = "blocked"
        with self.assertRaisesRegex(GameConfigError, "not ready"):
            render_game_config(plan)

    def test_invalid_sha_rejected(self):
        with self.assertRaisesRegex(GameConfigError, "SHA-256"):
            render_game_config(ready(sha="not-a-sha"))

    def test_non_exe_entry_rejected(self):
        with self.assertRaisesRegex(GameConfigError, "executable"):
            render_game_config(ready("Game.dll"))


if __name__ == "__main__":
    unittest.main()
