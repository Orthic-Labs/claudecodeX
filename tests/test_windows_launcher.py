import unittest
from pathlib import Path


class WindowsLauncherTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parents[1]
        windows = self.root / "windows"
        self.launcher = (windows / "launch.ps1").read_text(encoding="utf-8")
        self.installer = (windows / "install.ps1").read_text(encoding="utf-8")
        self.taskbar = (windows / "separate-taskbar.ps1").read_text(encoding="utf-8")
        self.wrapper = (windows / "anyclaude.vbs").read_text(encoding="utf-8")
        resolver = windows / "claude-install.ps1"
        self.resolver = resolver.read_text(encoding="utf-8") if resolver.exists() else ""
        self.readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.windows_docs = (self.root / "docs" / "windows.md").read_text(encoding="utf-8")

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

    def test_windows_resolves_both_official_managed_install_types(self):
        self.assertIn("Get-AppxPackage", self.resolver)
        self.assertIn("AnthropicClaude", self.resolver)
        self.assertIn("Update.exe", self.resolver)
        self.assertIn("app-*", self.resolver)
        self.assertIn("Get-AuthenticodeSignature", self.resolver)
        self.assertIn("Anthropic, PBC", self.resolver)
        self.assertNotIn("ClaudeStandalone", self.resolver)
        self.assertLess(
            self.resolver.index("AnthropicClaude"),
            self.resolver.index("Get-AppxPackage"),
            "the working Anthropic installer must win over a stale registered MSIX",
        )
        for consumer in (self.launcher, self.installer):
            self.assertIn("claude-install.ps1", consumer)
            self.assertIn("Resolve-ClaudeDesktopInstall", consumer)

    def test_squirrel_launches_the_current_versioned_binary_directly(self):
        self.assertIn("ExecutablePath = $currentExe", self.resolver)
        self.assertIn("$claude.ExecutablePath", self.launcher)
        self.assertIn("$claude.AsarPath", self.launcher)

    def test_hidden_wrapper_uses_a_reliable_runtime_and_reports_failure(self):
        self.assertIn(r"PowerShell\7\pwsh.exe", self.wrapper)
        self.assertIn("PSModulePath", self.wrapper)
        self.assertIn(", 0, True", self.wrapper)
        self.assertIn("WScript.Quit launchExitCode", self.wrapper)
        self.assertIn("launcher-error.log", self.launcher)

    def test_taskbar_icon_comes_from_the_shared_install_resolution(self):
        self.assertIn("IconResource", self.taskbar)
        self.assertNotIn("Get-AppxPackage", self.taskbar)
        self.assertIn("-IconResource $claude.IconResource", self.launcher)

    def test_windows_docs_cover_both_managed_installers(self):
        self.assertIn("Microsoft Store", self.windows_docs)
        self.assertIn("Anthropic's Windows installer", self.windows_docs)

    def test_readme_links_a_user_visible_changelog(self):
        changelog = self.root / "CHANGELOG.md"
        self.assertTrue(changelog.exists(), "CHANGELOG.md must exist at the repository root")
        self.assertIn("CHANGELOG.md", self.readme)


if __name__ == "__main__":
    unittest.main()
