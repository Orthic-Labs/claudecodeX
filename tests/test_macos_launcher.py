import json
import os
import subprocess
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

    def _run_share_block(self, home, config, environment=None):
        """Execute the launcher's skills/agents linking block against a fake HOME."""
        marker = 'if [ "${ANYCLAUDE_SHARE_CLAUDE_CODE:-1}" = 1 ]; then'
        block = marker + self.launcher.split(marker, 1)[1].split("\nfi\n", 1)[0] + "\nfi\n"
        subprocess.run(
            ["sh", "-e", "-c", block],
            check=True,
            env={
                "PATH": os.environ["PATH"],
                "HOME": str(home),
                "CONFIG": str(config),
                **(environment or {}),
            },
        )

    @unittest.skipIf(os.name == "nt", "POSIX symlink behavior requires a POSIX host")
    def test_skills_and_agents_are_shared_without_leaking_settings(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            config = Path(root) / "config"
            config.mkdir(parents=True)
            for share in ("skills", "agents"):
                (home / ".claude" / share).mkdir(parents=True)
            (home / ".claude" / "settings.json").write_text('{"model": "opus"}')

            self._run_share_block(home, config)

            for share in ("skills", "agents"):
                self.assertTrue((config / share).is_symlink())
                self.assertEqual(
                    (config / share).resolve(), (home / ".claude" / share).resolve()
                )
            # A pinned Anthropic-only model must never follow the skills into the gateway profile.
            self.assertFalse((config / "settings.json").exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink behavior requires a POSIX host")
    def test_share_repairs_a_stale_link_but_never_clobbers_a_real_directory(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            config = Path(root) / "config"
            config.mkdir(parents=True)
            (home / ".claude" / "skills").mkdir(parents=True)
            (home / ".claude" / "agents").mkdir(parents=True)

            # A link left pointing at a profile that no longer exists must re-point, not stay broken.
            (config / "skills").symlink_to(Path(root) / "gone")
            # A real directory is the user's own state: linking over it would destroy it.
            (config / "agents").mkdir()
            (config / "agents" / "mine.md").write_text("keep me")

            self._run_share_block(home, config)

            self.assertEqual(
                (config / "skills").resolve(), (home / ".claude" / "skills").resolve()
            )
            self.assertFalse((config / "agents").is_symlink())
            self.assertEqual((config / "agents" / "mine.md").read_text(), "keep me")

    @unittest.skipIf(os.name == "nt", "POSIX symlink behavior requires a POSIX host")
    def test_share_can_be_sealed_off(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            config = Path(root) / "config"
            config.mkdir(parents=True)
            (home / ".claude" / "skills").mkdir(parents=True)

            self._run_share_block(
                home, config, {"ANYCLAUDE_SHARE_CLAUDE_CODE": "0"}
            )

            self.assertFalse((config / "skills").exists())


if __name__ == "__main__":
    unittest.main()
