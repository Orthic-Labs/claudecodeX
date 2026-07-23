# Contributing

ClaudeCodeX is a small, standard-library proxy plus two launchers. The most useful contribution is a
new provider that people can actually use, so that flow is documented first.

## Add a provider

Every provider is one JSON template in [`examples/`](examples/). The proxy only renames the incoming
`claude-*` model to the provider's real model name and forwards the request, so a provider works as
soon as its template is correct.

1. **Copy the closest existing template.** MiniMax is the verified reference; GLM and Kimi show the
   untested shape.

   ```bash
   cp examples/minimax.json examples/yourprovider.json
   ```

2. **Fill in the upstream block** from the provider's own Anthropic-compatible docs:

   | Field | What it is |
   |---|---|
   | `host` | API hostname, no scheme (for example `api.minimax.io`) |
   | `prefix` | Path prefix the provider serves the Messages API under (for example `/anthropic`) |
   | `scheme` | `https` for a hosted provider, `http` for a local gateway |
   | `auth_header` | The header the provider reads the key from, usually `x-api-key` or `authorization` |
   | `key_env` | The environment variable **you** will store the key in. Never the key itself. |

3. **Map the models.** `default` is the fallback; other keys (`haiku`, and so on) match a keyword in
   the incoming Claude model name. Point each at a real provider model and pick a `thinking` policy
   (`adaptive`, `disabled`, or the provider's supported value).

4. **Verify it against the running proxy**, not just by eye:

   ```bash
   cp examples/yourprovider.json config.json
   export YOURPROVIDER_API_KEY="..."     # the name must match key_env
   python3 proxy.py &
   curl -fsS http://127.0.0.1:8801/health
   curl -fsS http://127.0.0.1:8801/v1/messages \
     -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
     -d '{"model":"claude-opus-4-8","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}'
   ```

   A successful `/v1/messages` that names your provider's model is the only proof that counts. The
   Desktop "Test connection" button probes `/v1/models`, which many gateways do not serve, so it is
   not evidence.

5. **Open the PR.** Include the template, and in the description say exactly what you verified: which
   OS, Claude Code or Desktop, and that a real `/v1/messages` returned the provider model. If you
   verified it end to end, flip that provider's row in the README **Provider status** table from
   untested to verified in the same PR. Untested providers must stay labeled untested.

## Change the proxy or launchers

Run the full check before opening a PR:

```bash
python3 -m py_compile proxy.py
python3 -m unittest discover -s tests -v
sh -n mac/claudecodex-macos.sh
for file in examples/*.json configLibrary/*.json; do python3 -m json.tool "$file" >/dev/null || exit 1; done
git diff --check
```

Repository invariants (localhost-only binding, no third-party runtime dependencies, no committed
keys, profile isolation, no unproven verified-provider claims, no em dashes in product copy) live in
[`AGENTS.md`](AGENTS.md). Read it before touching `proxy.py` or a launcher.

Add every user-visible fix or behavior change to [`CHANGELOG.md`](CHANGELOG.md). Use `Unreleased`
while work is pending, or a dated entry when the change is published directly to `main`.

## Reporting

Provider that does not work, a launcher that opens the wrong profile, or a docs error: open an issue
with your OS, your Claude Desktop version, and the relevant lines from `proxy.log`. Never paste a
provider key.
