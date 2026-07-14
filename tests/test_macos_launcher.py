import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MacLauncherTest(unittest.TestCase):
    def setUp(self):
        self.launcher = (
            Path(__file__).parents[1] / "mac" / "anyclaude-macos.sh"
        ).read_text()

    def test_profile_state_is_isolated_and_seed_uses_repo_root(self):
        self.assertIn('CONFIG="$PROFILE/claude-config"', self.launcher)
        self.assertIn('COWORK_FILES="$PROFILE/cowork-user-files"', self.launcher)
        self.assertEqual(
            self.launcher.count('CLAUDE_CONFIG_DIR="$CONFIG"'), 2
        )
        self.assertIn('SEED="$ROOT/configLibrary"', self.launcher)
        self.assertNotIn('pwd)/configLibrary', self.launcher)

    def test_default_cowork_path_moves_but_custom_path_is_preserved(self):
        marker = '"$PYTHON" - "$DESKTOP_CONFIG" "$COWORK_FILES" <<\'PY\'\n'
        configure_profile = self.launcher.split(marker, 1)[1].split(
            "\nPY\n", 1
        )[0]

        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "claude_desktop_config.json"
            cowork_files = Path(root) / "cowork-user-files"
            config.write_text(
                json.dumps(
                    {
                        "keep": True,
                        "coworkUserFilesPath": str(Path.home() / "Claude"),
                    }
                )
            )
            with patch.object(
                sys, "argv", ["configure-profile", str(config), str(cowork_files)]
            ):
                exec(configure_profile, {"__name__": "__main__"})
            self.assertEqual(
                json.loads(config.read_text()),
                {"keep": True, "coworkUserFilesPath": str(cowork_files)},
            )

            custom = str(Path(root) / "custom-cowork")
            config.write_text(
                json.dumps({"keep": True, "coworkUserFilesPath": custom})
            )
            with patch.object(
                sys, "argv", ["configure-profile", str(config), str(cowork_files)]
            ):
                exec(configure_profile, {"__name__": "__main__"})
            self.assertEqual(
                json.loads(config.read_text())["coworkUserFilesPath"], custom
            )

    def test_routing_check_uses_configured_port_without_paid_inference(self):
        self.assertIn('"http://127.0.0.1:$PORT/health"', self.launcher)
        self.assertNotIn('"model":"anyclaude', self.launcher)


if __name__ == "__main__":
    unittest.main()
