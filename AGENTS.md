# AGENTS.md: anyclaude

## Product contract

`anyclaude` lets Claude Code or Claude Desktop use an Anthropic-compatible provider by translating incoming Anthropic-shaped model names into provider model names. Keep the proxy local, provider-neutral, standard-library only, and explicit about what has actually been tested.

## Repository map

- `proxy.py`: request forwarding, model routing, thinking policy, localhost server
- `examples/*.json`: provider templates; unverified providers must stay labeled untested
- `configLibrary/`: secret-free Claude Desktop Gateway seed
- `mac/anyclaude-macos.sh`: isolated macOS Desktop launcher
- `windows/`: Windows launcher, installer, and taskbar separation
- `docs/windows.md`: Windows simultaneous-use, isolation, and removal guide
- `docs/macos.md`: Mac isolation and managed-sandbox policy

## Invariants

- Never commit provider keys, `.env`, `config.json`, or logs.
- Keep the proxy bound to `127.0.0.1`.
- Keep `proxy.py` free of third-party runtime dependencies.
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
python3 -m py_compile proxy.py
python3 -m unittest discover -s tests -v
sh -n mac/anyclaude-macos.sh
for file in examples/*.json configLibrary/*.json; do
  python3 -m json.tool "$file" >/dev/null || exit 1
done
git diff --check
```

For proxy behavior, copy an example to the ignored `config.json`, provide the named key environment variable, start `python3 proxy.py`, and send the README's `/v1/messages` request. Do not use a live paid request unless the task requires it and the operator has supplied the provider key.

For Claude Desktop behavior, verify the stock subscription profile remains untouched and the isolated process receives both profile environment variables. On macOS, also verify `coworkUserFilesPath` resolves inside the isolated profile.

## Documentation standard

The README is the human entry point. Its first viewport must establish **one desktop, two live Claude sessions**, show real proof, and point directly to the second-window setup. Put platform-specific policy and diagnostics in `docs/`; link them at the exact failure point. Commands must state whether they make a paid request, mutate machine-wide settings, or require administrator access.
