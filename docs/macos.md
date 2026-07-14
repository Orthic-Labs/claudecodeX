# macOS setup and Claude Desktop sandbox policy

The macOS launcher opens an isolated anyclaude profile beside the normal subscription Claude app, so both sessions can remain active on one Mac. This guide covers isolated profiles, GUI environment variables, case-insensitive paths, and Claude Desktop's managed Bash sandbox.

## Daily use

1. Start the localhost proxy.
2. Open **Claude** normally for the Anthropic subscription session.
3. Open `/Applications/anyclaude.app` for the gateway-backed session.

Both use the installed Claude Desktop binary, but their Desktop, embedded Claude Code, and default Cowork state remain separate.

## Install the isolated Dock launcher

Prerequisites:

- Claude Desktop at `/Applications/Claude.app`
- Python 3 available as `python3`
- A working `config.json` and provider key
- The proxy already running on the configured localhost port

From the repository root:

```bash
./mac/anyclaude-macos.sh --install-app
```

This creates `/Applications/anyclaude.app`. It is a small launcher, not a second Claude installation. Claude Desktop continues to update normally.

Run without installing the Dock launcher:

```bash
./mac/anyclaude-macos.sh
```

The default profile is `~/ClaudeProfiles/anyclaude-profile`. Override it with `ANYCLAUDE_PROFILE`.

## What the launcher isolates

| State | Location |
|---|---|
| Claude Desktop profile | `~/ClaudeProfiles/anyclaude-profile` |
| Claude Code config/runtime | `~/ClaudeProfiles/anyclaude-profile/claude-config` |
| Cowork-owned files | `~/ClaudeProfiles/anyclaude-profile/cowork-user-files` |
| Gateway model seed | `~/ClaudeProfiles/anyclaude-profile/configLibrary` |

Both `CLAUDE_USER_DATA_DIR` and `CLAUDE_CONFIG_DIR` are intentionally set. Isolating only Desktop state is insufficient when `~/.claude` resolves inside a selected workspace.

The launcher also migrates only Cowork's default `~/Claude` location. On a case-insensitive Mac, `~/Claude` and `~/claude` are the same directory; if the latter is your repository, Desktop otherwise rejects it as protected storage. A custom Cowork location is preserved.

## What the launcher shares

| State | Shared how |
|---|---|
| `~/.claude/skills` | Symlinked into the isolated `claude-config`, refreshed on every launch |
| `~/.claude/agents` | Symlinked into the isolated `claude-config`, refreshed on every launch |

Isolation is for auth and Desktop state, not for your skill library. Without these links the isolated `CLAUDE_CONFIG_DIR` contains no `skills/` or `agents/` at all, so Claude Code inside the anyclaude window silently has none of the skills and subagents you installed. They are linked rather than copied, so `~/.claude` stays the single source of truth and edits appear in both instances. The launcher re-points a stale link but never overwrites a real directory you placed there.

`settings.json` is deliberately not shared. It commonly pins an Anthropic-only model name that the gateway provider does not serve, so linking it would fight the gateway route. Hooks defined there therefore do not run in the anyclaude window. Set `ANYCLAUDE_SHARE_CLAUDE_CODE=0` to seal the profile completely.

## Provider keys and GUI apps

A process opened from Finder or the Dock does not reliably inherit exports from `~/.zshrc`. The safest first-run workflow is:

1. Export the provider key in a terminal.
2. Start `python3 proxy.py` there and leave it running.
3. Open `/Applications/anyclaude.app`.

If a login service starts the proxy, put the export in the login environment it actually loads, commonly `~/.zprofile`. Never put the provider key in `config.json`, the Gateway seed, an AppleScript app, or a LaunchAgent plist.

## Make blocked Bash operations ask instead of hard-deny

### Why this is needed

Claude Desktop may launch its embedded Claude Code with host-managed settings equivalent to:

```json
{
  "sandbox": {
    "enabled": true,
    "allowUnsandboxedCommands": false,
    "network": {
      "allowedDomains": ["127.0.0.1", "api.anthropic.com"],
      "allowManagedDomainsOnly": true
    }
  }
}
```

`allowManagedDomainsOnly` ignores domains added by user or project settings. A blocked `git`, `curl`, or other Bash subprocess therefore receives a hard proxy denial such as:

```text
CONNECT tunnel failed, response 403
```

“Bypass permissions” changes tool approval behavior; it does not remove this managed sandbox boundary.

### Safer policy: sandbox first, approval on escape

Claude Code supports a system managed-settings file at:

```text
/Library/Application Support/ClaudeCode/managed-settings.json
```

If that file already exists, merge the fields below into it. Do not overwrite an organization's policy. For a personal Mac with no existing file:

```bash
sudo install -d -m 755 "/Library/Application Support/ClaudeCode"

sudo tee "/Library/Application Support/ClaudeCode/managed-settings.json" >/dev/null <<'JSON'
{
  "parentSettingsBehavior": "first-wins",
  "env": {
    "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1"
  },
  "permissions": {
    "allow": ["WebFetch(domain:127.0.0.1)"]
  },
  "sandbox": {
    "enabled": true,
    "allowUnsandboxedCommands": true,
    "network": {
      "allowedDomains": ["127.0.0.1", "api.anthropic.com"],
      "allowManagedDomainsOnly": false
    }
  }
}
JSON

python3 -m json.tool \
  "/Library/Application Support/ClaudeCode/managed-settings.json" >/dev/null \
  && echo "Managed settings installed"
```

This keeps the Bash sandbox enabled while allowing new domains or an unsandboxed retry to enter the normal permission flow. It does **not** make every Bash command unrestricted.

`parentSettingsBehavior: "first-wins"` makes the system policy take precedence over policy supplied by an embedding host such as Claude Desktop. The file repeats the host's localhost permission and marketplace-autoinstall restriction so they are not lost.

### Restart and verify

1. Quit Claude Desktop completely with `Command-Q`.
2. Reopen the isolated Gateway instance.
3. Select **Default** or **Accept Edits**, not **Bypass permissions**.
4. Run `/status`; setting sources should include `Enterprise managed settings (file)`.
5. Ask Claude Code to run:

```bash
git ls-remote https://github.com/bogusyogi/anyclaude.git HEAD
```

The first access should enter the approval flow instead of failing immediately with a CONNECT 403.

### Security trade-off

This policy is safer than disabling the sandbox: commands begin inside the sandbox and crossing its boundary requires the regular permission system. Approval still grants real access under your macOS user account. Treat prompts from untrusted repositories as security decisions and do not combine this policy with **Bypass permissions**.

Server-managed or MDM policy outranks the local file and may prevent this change on an organization-managed Mac.

### Roll back

Only remove the file if you created it for this setup and it contains no other policy:

```bash
sudo rm "/Library/Application Support/ClaudeCode/managed-settings.json"
```

Quit and reopen Claude Desktop after changing the policy.

## Mac-specific troubleshooting

### Folder selection says the repository is protected

Confirm the running Claude process has both isolated variables:

```bash
ps eww -ax | grep '[C]laude.app/Contents/MacOS/Claude' | \
  grep -o 'CLAUDE_\(USER_DATA_DIR\|CONFIG_DIR\)=[^ ]*'
```

Both paths should point inside `~/ClaudeProfiles/anyclaude-profile`.

### Dock launcher opens subscription Claude

Claude Desktop's undocumented `CLAUDE_USER_DATA_DIR` behavior may have changed. The launcher checks the installed app bundle and stops with a warning instead of silently opening the subscription profile.

### Dock icon is stale

Run `./mac/anyclaude-macos.sh --install-app` again. The installer refreshes LaunchServices after replacing the wrapper icon.
