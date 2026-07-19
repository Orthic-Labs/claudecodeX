# Changelog

User-visible changes to anyclaude are recorded here. The project does not yet use numbered releases, so entries are grouped by date.

## Unreleased

## 2026-07-19

### Fixed

- Windows now supports both official updater-managed Claude Desktop installations: Microsoft Store/MSIX and Anthropic's non-admin Windows installer.
- When both remain registered, Windows prefers the complete Anthropic updater installation instead of an abandoned or partially removed MSIX package.
- The isolated launcher resolves the newest signed `app-*\claude.exe` after an Anthropic installer update, so anyclaude follows normal Claude updates without a manual reinstall.
- The Windows shortcut now uses a reliable hidden PowerShell runtime, preserves the built-in Windows PowerShell module path when needed, and reports launcher failures instead of silently doing nothing.
- Installer shortcuts and the separate taskbar identity now use the same resolved Claude executable and icon.

### Security

- Windows rejects manually extracted or unsigned Claude executables. Only binaries with a valid Anthropic signature from an official managed installation are launched.
