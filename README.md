# anyclaude

**Run Claude Code and Claude Desktop on any Anthropic-compatible model — MiniMax, GLM, Kimi, DeepSeek, or a local model.** Keep your Anthropic subscription; add a second, cheaper (or free-tier) brain beside it.

Providers like [MiniMax](https://platform.minimax.io/docs/token-plan/claude-code), Zhipu GLM, and Moonshot Kimi ship **Anthropic-format endpoints** and document using them from Claude Code. `anyclaude` is a tiny stdlib-only proxy that makes that work across **all three surfaces** — the CLI, the desktop app pointed directly at it, or a **second isolated desktop window running side by side with your subscription Claude**.

```
Claude Code / Claude Desktop  --claude-*-->  anyclaude proxy :8801  --<your model>-->  provider
```

No fork, no patched binary, no extra Electron download.

---

## Why a proxy at all?

Every surface sends Anthropic-shaped model names (`claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-*`). Claude **Desktop** additionally *validates* that the configured model looks Anthropic and rejects `MiniMax-M3` / `glm-4.7` outright. So something has to rename the model on the way through. That rename — plus a per-model thinking policy and injecting your key from an env var — is all the proxy does.

## Status

| Provider | Endpoint | Verified |
|---|---|---|
| **MiniMax** (M3) | `api.minimax.io/anthropic` | ✅ CLI + Desktop, Windows & macOS |
| Zhipu **GLM** | `open.bigmodel.cn/api/anthropic` | ⚠️ config provided, untested — PRs welcome |
| Moonshot **Kimi** | `api.moonshot.ai/anthropic` | ⚠️ config provided, untested |
| **Local** (LiteLLM / vLLM / Ollama) | `127.0.0.1:<port>` | ⚠️ config provided, untested |

Only MiniMax is tested (the author's key). The mechanism is identical for the rest — run one, send a PR flipping it to ✅.

---

## 1. Configure (once, shared by every surface)

```bash
cp examples/minimax.json config.json      # or glm.json / kimi.json / local.json
```

```json
{
  "port": 8801,
  "upstream": { "host": "api.minimax.io", "prefix": "/anthropic",
                "scheme": "https", "auth_header": "x-api-key", "key_env": "MINIMAX_API_KEY" },
  "models": {
    "default": { "name": "MiniMax-M3", "thinking": "adaptive" },
    "haiku":   { "name": "MiniMax-M3", "thinking": "disabled" }
  }
}
```

- **`key_env`** — the *name* of the env var holding your key. The key is never written to disk or committed; the proxy reads it at runtime.
- **`models`** — a keyword found in the incoming `claude-*` name → an upstream model + thinking policy. `default` is the fallback; a `haiku` entry with `"thinking": "disabled"` gives a no-reasoning fast lane. Point tiers at *different* upstream models for real routing (e.g. GLM `glm-4.7` vs `glm-4.7-flash`).

Set your key (never goes in the repo):

```bash
# macOS/Linux — add to ~/.zshrc or ~/.bashrc
export MINIMAX_API_KEY="sk-..."
```
```powershell
# Windows — persists across reboots; open a new terminal after
setx MINIMAX_API_KEY "sk-..."
```

Start the proxy:

```bash
python proxy.py            # foreground, to watch it
# or background it / autostart it — see the installers below
```

Verify it routes (the one real test — "Test connection" buttons lie):

```bash
curl -s http://127.0.0.1:8801/v1/messages -H "x-api-key: router-dummy" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}'
# -> "model":"MiniMax-M3" ... means it's live
```

---

## 2. Pick your surface

### A. Claude Code (CLI) — simplest, no isolation needed

Point Claude Code at the proxy with env vars (the provider's own docs describe the same thing, minus the rename):

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8801"
export ANTHROPIC_AUTH_TOKEN="router-dummy"          # placeholder; real key is in the proxy's env
export ANTHROPIC_MODEL="claude-opus-4-8"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-haiku-4-5-20251001"
claude
```

Wrap those in a shell alias (`anyclaude`) so plain `claude` stays on your subscription. `/status` inside Claude Code should show the proxy URL.

### B. Claude Desktop, direct — replaces your subscription in the app until you switch back

Developer → Configure Third-Party Inference:

- Provider **Gateway**, Base URL `http://127.0.0.1:8801`, Credential kind **Static API key**, key `router-dummy`, Auth scheme **x-api-key**, Model discovery **off**.
- Add models with **Anthropic** names (`claude-opus-4-8` → tier opus, default; add `claude-haiku-4-5-20251001` → tier haiku for the fast lane). The proxy renames them upstream.

Switch back to Anthropic anytime by setting the provider to Anthropic. Simple, but it's one-at-a-time.

### C. Claude Desktop, second instance — run both at once, side by side ⭐

The headline feature: a fully isolated second Claude Desktop with its own profile and its own taskbar button, on your gateway model, while your subscription Claude keeps running untouched.

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File windows\install.ps1   # shortcut + hidden proxy autostart
```
**macOS:**
```bash
./mac/anyclaude-macos.sh --install-app     # puts an "anyclaude" launcher in /Applications (Claude's icon)
./mac/anyclaude-macos.sh                    # or just run it directly
```

Then click the shortcut / app. A fresh window opens with its own taskbar (Windows) / Dock (macOS) entry. The launcher seeds the gateway config into the new profile automatically (from `configLibrary/`, no secrets) — **so on Windows you can skip the settings UI, and on macOS you must, because the Mac build has no Developer menu; the config file is the only interface.**

> **Do not sign in first.** Gateway mode needs no Anthropic login, and an OAuth `claude://` deep link lands in the *default* profile, not the isolated one. The seeded config means you never need to.

---

## The four things that will bite you (all surfaces)

1. **The Gateway/AUTH_TOKEN field must be a placeholder** (`router-dummy`). Your real key is injected by the proxy from its env var. Putting the real key in the app means it bypasses the proxy's rename and fails.
2. **Isolation is via `CLAUDE_USER_DATA_DIR`** (surface C). The launcher sets it so the second instance gets its own profile *and* single-instance lock. It's an **undocumented** Anthropic env var — a Desktop update could drop it; the launchers detect that and warn instead of silently opening a normal Claude.
3. **`Claude-3p` is the canary (Desktop).** If you ever apply a gateway config to your *stock* app without the env var, Desktop relocates to `%LOCALAPPDATA%\Claude-3p` (macOS: `~/Library/Application Support/Claude-3p`) and boots into gateway mode. If that dir appears, isolation broke — delete it; your subscription profile (`Claude`) is untouched.
4. **"Test connection" is a false negative.** It probes `/v1/models`, which many gateways don't serve. Ignore it — the only proof is a `status=200` line in `proxy.log` (or the curl above).

## Separate taskbar / Dock button (surface C)

Claude Desktop never sets an AppUserModelID, so both instances would otherwise group together. On **Windows**, `separate-taskbar.ps1` sets a per-window AUMID (`PKEY_AppUserModel_ID`) so the second instance gets its own button, keeping Claude's icon; the launcher re-applies it each start (the AUMID lives on the window handle). On **macOS**, `--install-app` builds a tiny `osacompile` wrapper app that wears Claude's icon (copy `electron.icns`, delete `Assets.car`, `lsregister`) so the Dock and ⌘-Tab tell them apart.

## Security

- Your key lives only in an environment variable. `config.json` and `proxy.log` are gitignored. Nothing in this repo contains a key.
- The proxy binds `127.0.0.1` only — not reachable off your machine.

## License

MIT. Independent community tool, not affiliated with Anthropic or any model provider. Use each provider's API per its own terms — MiniMax, for one, [officially documents Claude Code use](https://platform.minimax.io/docs/token-plan/claude-code).
