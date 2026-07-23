# Windows: run two Claude Desktop sessions simultaneously

The Windows launcher opens an isolated ClaudeCodeX profile beside the normal subscription Claude app. It uses the installed Claude Desktop binary; it does not install, copy, or patch Claude.

## Install

Prerequisites:

- Claude Desktop installed from the Microsoft Store or [Anthropic's Windows installer](https://claude.com/download)
- Python 3.9+ with `pythonw.exe` on `PATH`
- `config.json` copied from a provider template
- The provider key saved as the user environment variable named by `upstream.key_env`

From PowerShell in the repository:

```powershell
Copy-Item examples\minimax.json config.json
setx MINIMAX_API_KEY "sk-..."
powershell -ExecutionPolicy Bypass -File windows\install.ps1
```

The launcher reads the user-level value written by `setx`, so you do not need to sign out before the first run. It never writes the key to the profile or Gateway config.

## Daily use

1. Open **Claude** normally for the Anthropic subscription session.
2. Open **ClaudeCodeX** from the Desktop or Start menu.
3. Keep both windows open. Their profiles, histories, and taskbar identities are separate.

The ClaudeCodeX shortcut starts the localhost proxy when needed, verifies `/health`, opens the isolated profile, and assigns the new window its own taskbar identity.

## What is isolated

| State | Location |
|---|---|
| Claude Desktop profile | `%LOCALAPPDATA%\ClaudeCodeX\profile` |
| Embedded Claude Code state | `%LOCALAPPDATA%\ClaudeCodeX\profile\claude-config` |
| Cowork-owned files | `%LOCALAPPDATA%\ClaudeCodeX\profile\cowork-user-files` |
| Gateway model seed | `%LOCALAPPDATA%\ClaudeCodeX\profile\configLibrary` |

The launcher sets both `CLAUDE_USER_DATA_DIR` and `CLAUDE_CONFIG_DIR`. It moves only Cowork's default location into the isolated profile; an existing custom Cowork path is preserved.

## What is shared

| State | Shared how |
|---|---|
| `~/.claude\skills` | Junction into the isolated `claude-config`, refreshed on every launch |
| `~/.claude\agents` | Junction into the isolated `claude-config`, refreshed on every launch |

Isolation is for auth and Desktop state, not for your skill library: without these links, Claude Code inside the ClaudeCodeX window would silently have no skills or subagents at all. Junctions are used because they need no elevation or Developer Mode. The launcher re-points a stale link but never overwrites a real directory you placed there.

`settings.json` is deliberately not shared. It commonly pins an Anthropic-only model name that the gateway provider does not serve. Hooks defined there therefore do not run in the ClaudeCodeX window. Set `CLAUDECODEX_SHARE_CLAUDE_CODE=0` to seal the profile completely.

## What the installer changes

- Creates `%USERPROFILE%\Desktop\ClaudeCodeX.lnk`
- Creates `%APPDATA%\Microsoft\Windows\Start Menu\Programs\ClaudeCodeX.lnk`
- Creates `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudeCodeX-proxy.vbs`
- Creates profile data under `%LOCALAPPDATA%\ClaudeCodeX` on first launch

No administrator access is required for ClaudeCodeX or Anthropic's non-admin installer. Claude Desktop continues to update through its normal managed installation. ClaudeCodeX resolves the current signed version on every launch, so it follows updates automatically.

## Remove it

Quit the ClaudeCodeX window, then run:

```powershell
Remove-Item "$env:USERPROFILE\Desktop\ClaudeCodeX.lnk" -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\ClaudeCodeX.lnk" -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ClaudeCodeX-proxy.vbs" -ErrorAction SilentlyContinue
```

To delete the isolated chats and settings too:

```powershell
Remove-Item "$env:LOCALAPPDATA\ClaudeCodeX" -Recurse
```

That last command is destructive and cannot be undone. It does not touch the normal Claude profile. Remove the provider environment variable separately only if nothing else uses it.

## Troubleshooting

### The shortcut says the proxy failed `/health`

Confirm `config.json` exists, `upstream.key_env` matches the saved environment-variable name, and the provider key is valid. Then inspect `proxy.log` without sharing its surrounding environment.

### Both windows share one taskbar button

Run `windows\launch.ps1` again. It reapplies the per-window AppUserModelID after the ClaudeCodeX window appears. If Claude Desktop changed its window process behavior, `windows\separate-taskbar.ps1` may need an update; profile isolation can still work even if Windows groups the icons.

### The launcher refuses to open Claude

It checks the installed Claude bundle for `CLAUDE_USER_DATA_DIR`. If a Desktop update removes that behavior, the launcher stops rather than silently opening the subscription profile and billing the wrong provider.

The launcher accepts official Microsoft Store/MSIX and Anthropic installer builds. It rejects manually extracted or unsigned copies. If the shortcut does nothing, inspect `%LOCALAPPDATA%\ClaudeCodeX\profile\launcher-error.log`; the shortcut also displays that path when launch fails.
