# Codex

ClaudeCodeX gives Codex CLI the same second-instance story it gives Claude: your
ChatGPT subscription in one terminal, a third-party provider in another, both live.

## Why a proxy is required

Codex 0.122 removed `wire_api = "chat"`. Every custom provider must now speak the
OpenAI **Responses** API:

```
`wire_api = "chat"` is no longer supported.
How to fix: set `wire_api = "responses"` in your provider config.
```

That string is in the shipping binary. Almost no third-party provider serves the
Responses API, so pointing Codex straight at Alibaba, GLM, DeepSeek, or Kimi fails.
ClaudeCodeX sits in the middle:

```text
codex --/v1/responses--> 127.0.0.1:8801 --/chat/completions--> your provider
```

`codex_bridge.py` converts the request (Responses `input` items to Chat `messages`,
tools, images, tool-call pairing) and converts the reply back into a Responses event
stream, so text, reasoning, and tool calls all arrive live rather than in one block.

## Setup

### 1. Configure the proxy

Your `config.json` needs a `codex` block naming the provider's OpenAI-compatible
endpoint. `examples/alibaba.json` is a working reference:

```json
"codex": {
  "host": "token-plan.ap-southeast-1.maas.aliyuncs.com",
  "prefix": "/compatible-mode/v1",
  "scheme": "https",
  "auth_header": "authorization",
  "key_env": "DASHSCOPE_API_KEY",
  "models": { "gpt-": { "name": "qwen3.7-max" } }
}
```

`models` is a keyword map like the Anthropic one, with one difference: a model name
that matches nothing and has no `default` entry is **passed through untouched**. That
is what makes `codex -m glm-5.2` work with no config change.

`key_env` defaults to the Anthropic upstream's key when omitted, so a provider that
serves both protocols needs only one key.

Without a `codex` block the proxy still runs, and `/v1/responses` answers `501` with
a pointer to this page instead of failing silently.

### 2. Register the provider

Add to `~/.codex/config.toml`:

```toml
[model_providers.ClaudeCodeX]
name = "ClaudeCodeX (local proxy)"
base_url = "http://127.0.0.1:8801/v1"
env_key = "CLAUDECODEX_PROXY_KEY"
wire_api = "responses"
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000
```

`env_key` must name a variable that exists, but the proxy holds the real key, so a
placeholder is correct here:

```bash
./mac/save-key.sh CLAUDECODEX_PROXY_KEY      # enter: proxy-dummy
```

This block is inert. Codex keeps using your subscription until a profile selects it.

### 3. Add a profile

Codex layers `$CODEX_HOME/<name>.config.toml` over the base config when you pass
`--profile`. Create `~/.codex/qwen.config.toml`:

```toml
model = "qwen3.7-max"
model_provider = "ClaudeCodeX"
```

### 3b. One profile per provider

Codex binds a single `model_provider` per session, so it cannot show your
subscription models and proxied models in one picker. Profiles are the way
around that: the provider block is shared, and each profile picks a model.

`~/.codex/mm.config.toml`:

```toml
model = "MiniMax-M3"
model_provider = "claudecodex"
```

`~/.codex/qwen.config.toml`:

```toml
model = "qwen3.7-max"
model_provider = "claudecodex"
```

```bash
codex            # your ChatGPT subscription, untouched
codex -p mm      # MiniMax
codex -p qwen    # Alibaba
```

The proxy routes on the model name, so both profiles reach different providers
through the same port and the same provider block. To make the models appear in
the picker rather than only working through `-m`, point `model_catalog_json` at
a catalog file; note that it replaces the built-in list rather than merging, so
keep it on the profile and not in the base config.

### 4. Run both

```bash
python3 proxy.py &      # one proxy serves Claude and Codex together
codex                   # your ChatGPT subscription, unchanged
codex -p qwen           # Alibaba, in a second terminal
codex -p qwen -m glm-5.2
codex -p qwen -m deepseek-v4-pro
```

Confirm the wiring without spending a request:

```bash
curl -fsS http://127.0.0.1:8801/health
```

`codex_upstream` in that payload is the endpoint `/v1/responses` will use.

## What carries across, and what does not

| Capability | Behavior |
|---|---|
| Streaming text | Live, as `response.output_text.delta` |
| Reasoning | Providers that emit `reasoning_content` (Qwen, DeepSeek, GLM) surface as a reasoning item |
| Function tools | Full support, including parallel calls and tool-call pairing |
| `apply_patch` | The freeform tool is converted to a single-string function and converted back |
| Images | `input_image` parts become OpenAI multipart content |
| Token usage | Mapped to Responses shape, including cached and reasoning token counts |
| Web search, image generation, local shell | Dropped, and logged. Codex still has its own shell tool |
| Parallel agents | Not available. Codex runs one model per session by design |

## Troubleshooting

### `stream disconnected before completion` or an idle timeout

The provider stopped mid-stream. `proxy.log` records the upstream status for the
request. Raise `stream_idle_timeout_ms` if the model is simply slow to first token.

### Codex reports a model error immediately

The proxy forwards the provider's real status and body rather than masking it, so the
message is the provider's own. A `400` naming the model usually means the id is not in
your plan; check it against the provider's model list.

### `failed to parse ResponseItem`

An item shape reached Codex that it did not recognize. Run the offline suite, which
asserts every emitted item shape:

```bash
python3 -m unittest discover -s tests -v
```

### Codex still uses your subscription

You omitted `--profile`, or the profile file is not at `~/.codex/<name>.config.toml`.
`codex --strict-config doctor` reports config problems without making a request.
