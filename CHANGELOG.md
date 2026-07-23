# Changelog

User-visible changes to ClaudeCodeX are recorded here. The project does not yet use numbered releases, so entries are grouped by date.

## Unreleased

### Fixed

- Providers that inline their reasoning in `<think>` tags (MiniMax M3 among them) no longer leak it into the answer. The tags are split out into a proper reasoning item, including when a tag straddles two stream chunks, so Codex shows thinking separately instead of prefixing every reply with it.
- A `_comment` key inside `providers` or `models` no longer crashes startup. The example configs shipped in this repository use them, so a valid file could fail to load. A test now starts the proxy against every file in `examples/`.
- One provider with an unsaved key no longer stops the others. Missing keys are a startup warning, and only routes needing that key fail, with a 503 naming both the environment variable and the Keychain service.

### Added

- macOS Keychain support. A provider can name a `keychain` service instead of relying on a dotfile, so the key never sits in plaintext in `~/.zprofile`, a launchd plist, shell history, or `ps` output. `mac/save-key.sh` stores it with `security add-generic-password` and verifies the read back.
- An environment variable always wins over the Keychain, so a single config file works unchanged on macOS and on Windows, where `windows/save-key.ps1` writes a User-scope variable.
- Multiple providers behind one proxy. A new `providers` block names as many endpoints as you own, and every route picks its own with `"provider": "<name>"`, so one Claude window or one Codex session can reach MiniMax, Alibaba, and others at the same time. See `examples/multi-provider.json`.
- `"auth": "passthrough"` forwards the caller's own credentials instead of a stored key, so a route can reach your real Anthropic subscription through the same proxy. This is what lets one model alias go to a third-party provider while the rest of the session stays on your subscription.
- Route keys accept alternatives: `"qwen|glm|deepseek|kimi"` matches any of them.
- `"name": "passthrough"` keeps the model id the client sent, so `codex -m glm-5.2` reaches a multi-model provider unchanged.
- Only providers you actually route to require their key, so one config can list every provider you own without forcing every key to be present.
- `/health` now reports each provider's base URL and the resolved `provider:model` for every route.
- Codex CLI support. A new `/v1/responses` front end accepts the OpenAI Responses API that Codex 0.122+ requires and translates to Chat Completions upstream, so `codex -p <profile>` runs on a third-party provider while plain `codex` stays on your ChatGPT subscription. Setup is in `docs/codex.md`.
- `codex_bridge.py` converts Responses input items, tools, images, and tool-call pairing into Chat Completions, and converts streamed text, reasoning, tool calls, and token usage back into Responses events.
- Freeform `custom` tools, which Codex uses for `apply_patch`, survive the round trip as a single-string function and are restored as `custom_tool_call` items.
- `examples/alibaba.json` for Alibaba Cloud Model Studio Token Plan. One key serves Claude through `/apps/anthropic` and Codex through `/compatible-mode/v1`, covering the Qwen, DeepSeek, GLM, Kimi, and MiniMax models in that plan.
- `mac/save-key.sh` and `windows/save-key.ps1` save a provider key to the login environment with the input hidden, so it stays out of shell history and out of the repository. Re-running one rotates the key in place.
- `GET /v1/models` lists the configured models for clients that probe it.

### Changed

- Responses are now streamed through instead of buffered, so Claude renders tokens as they arrive rather than after the full answer.
- A model name that matches no route and has no `default` entry now passes through untouched. This lets one Codex configuration reach every model a multi-model provider serves.
- `codex.key_env` falls back to the Anthropic upstream's key, so a provider serving both protocols needs only one key.
- `anthropic-beta` request headers are forwarded upstream.
- A new optional `extra_body` field on either upstream merges provider-specific parameters into the outgoing request.

## 2026-07-19

### Fixed

- Windows now supports both official updater-managed Claude Desktop installations: Microsoft Store/MSIX and Anthropic's non-admin Windows installer.
- When both remain registered, Windows prefers the complete Anthropic updater installation instead of an abandoned or partially removed MSIX package.
- The isolated launcher resolves the newest signed `app-*\claude.exe` after an Anthropic installer update, so ClaudeCodeX follows normal Claude updates without a manual reinstall.
- The Windows shortcut now uses a reliable hidden PowerShell runtime, preserves the built-in Windows PowerShell module path when needed, and reports launcher failures instead of silently doing nothing.
- Installer shortcuts and the separate taskbar identity now use the same resolved Claude executable and icon.

### Security

- Windows rejects manually extracted or unsigned Claude executables. Only binaries with a valid Anthropic signature from an official managed installation are launched.
