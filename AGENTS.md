# AGENTS.md: anyclaude

## Product contract

`anyclaude` lets Claude Code, Claude Desktop, or Codex CLI use a third-party provider. For Claude it translates incoming Anthropic-shaped model names into provider model names. For Codex it serves the OpenAI Responses API that Codex requires and translates to Chat Completions upstream. Keep the proxy local, provider-neutral, standard-library only, and explicit about what has actually been tested.

## Repository map

- `proxy.py`: request forwarding, model routing, thinking policy, streaming, localhost server
- `codex_bridge.py`: Responses to Chat Completions translation, pure functions plus one stream state machine
- `mac/save-key.sh`, `windows/save-key.ps1`: hidden-input key persistence
- `docs/codex.md`: Codex setup, capability table, troubleshooting
- `examples/*.json`: provider templates; unverified providers must stay labeled untested
- `configLibrary/`: secret-free Claude Desktop Gateway seed
- `mac/anyclaude-macos.sh`: isolated macOS Desktop launcher
- `windows/`: Windows launcher, installer, and taskbar separation
- `docs/windows.md`: Windows simultaneous-use, isolation, and removal guide
- `docs/macos.md`: Mac isolation and managed-sandbox policy

## Invariants

- Never commit provider keys, `.env`, `config.json`, or logs.
- Keep the proxy bound to `127.0.0.1`.
- Keep `proxy.py` and `codex_bridge.py` free of third-party runtime dependencies.
- Keep `codex_bridge.py` free of network calls so every translation rule stays unit testable offline.
- Never emit a Responses item shape that is not asserted by a test in `tests/test_codex_bridge.py`. Codex rejects unknown item shapes with `failed to parse ResponseItem`.
- Codex custom providers must use `wire_api = "responses"`. `wire_api = "chat"` is rejected by the Codex binary; do not document it as an option.
- Preserve both `CLAUDE_USER_DATA_DIR` and `CLAUDE_CONFIG_DIR` isolation.
- Keep the simultaneous-use promise literal: the normal subscription profile must remain untouched while the isolated instance runs.
- Preserve custom Cowork storage; migrate only the default `~/Claude` path.
- Keep `/health` local and side-effect-free; launcher readiness must not consume inference.
- Never claim a provider/platform combination is verified without real evidence.
- Never use em dashes in README or product copy. Use periods, commas, colons, or parentheses.
- Do not treat Desktop's `/v1/models` probe as a routing test; verify `/v1/messages`.

## Verification

Run before proposing a change:

```bash
python3 -m py_compile proxy.py codex_bridge.py
python3 -m unittest discover -s tests -v
sh -n mac/anyclaude-macos.sh mac/save-key.sh
for file in examples/*.json configLibrary/*.json; do
  python3 -m json.tool "$file" >/dev/null || exit 1
done
git diff --check
```

`tests/test_proxy.py` starts the proxy against a fake Chat Completions server and
asserts the full Responses event sequence, so the Codex path is provable offline
without a provider key or a paid request.

For proxy behavior, copy an example to the ignored `config.json`, provide the named key environment variable, start `python3 proxy.py`, and send the README's `/v1/messages` request. Do not use a live paid request unless the task requires it and the operator has supplied the provider key.

For Claude Desktop behavior, verify the stock subscription profile remains untouched and the isolated process receives both profile environment variables. On macOS, also verify `coworkUserFilesPath` resolves inside the isolated profile.

## Documentation standard

The README is the human entry point. Its first viewport must establish **one desktop, two live Claude sessions**, show real proof, and point directly to the second-window setup. Put platform-specific policy and diagnostics in `docs/`; link them at the exact failure point. Commands must state whether they make a paid request, mutate machine-wide settings, or require administrator access.

Record every user-visible fix or behavior change in the root `CHANGELOG.md` under `Unreleased` or a dated release entry, and keep the README's changelog link visible.

## User intent is final (workspace rule, locked 2026-07-19)

An explicit user request is the approval for every step of it. This repo's gates (bakeoff, release, QA, review) govern only unrequested spend, destructive/production steps, or specifics the user must see (e.g. a run packet) — and then only that single step; all other requested work is completed first, never left undone pending approval. Offering is the same defect as asking: "say the word and I'll trace it" / "let me know and I'll do it" — if it is in scope of the request, do it and report what you found; an unresolved "I have not found X" at the end of a turn is unfinished work, not a status report. Supersedes any stricter reading of this repo's gates. Canonical: workspace `CLAUDE.md` §1C / `AGENTS.md` "User Intent Is Final".

## No solution + caveat (workspace rule, locked 2026-07-19)

Work is either in perfect shape or it needs fixing — and if it needs fixing, fix it now, in this turn. Never close a reply with a hedge ("one thing worth flagging", "one caveat", "the honest limit is", "that said…"). Three legitimate endings only: done and verified with evidence; a genuine failure stated in the body with the real output; or a hard blocker naming the input required. If a caveat is worth writing, it is worth fixing first. Canonical: workspace `CLAUDE.md` §1D / `AGENTS.md` "No Solution + Caveat".
