import unittest
from pathlib import Path


class WindowsLauncherTest(unittest.TestCase):
    def setUp(self):
        self.launcher = (
            Path(__file__).parents[1] / "windows" / "launch.ps1"
        ).read_text()

    def test_second_instance_isolates_desktop_code_and_cowork_state(self):
        self.assertIn("CLAUDE_USER_DATA_DIR", self.launcher)
        self.assertIn("CLAUDE_CONFIG_DIR", self.launcher)
        self.assertIn("coworkUserFilesPath", self.launcher)
        self.assertIn("claude-config", self.launcher)
        self.assertIn("cowork-user-files", self.launcher)

    def test_launcher_verifies_the_proxy_health_endpoint(self):
        self.assertIn("/health", self.launcher)
        self.assertIn("Invoke-RestMethod", self.launcher)

    def test_launcher_reads_a_setx_key_without_requiring_sign_in(self):
        self.assertIn("upstream.key_env", self.launcher)
        self.assertIn("GetEnvironmentVariable($keyEnv, 'User')", self.launcher)
        self.assertIn("SetEnvironmentVariable($keyEnv, $storedKey, 'Process')", self.launcher)


if __name__ == "__main__":
    unittest.main()
