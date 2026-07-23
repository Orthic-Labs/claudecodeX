"""Local model proxy for Claude Desktop, Claude Code, and Codex.

Two front ends, one process, one provider key:

    Claude Desktop / Claude Code --/v1/messages--> proxy --> Anthropic-format provider
    Codex CLI                    --/v1/responses-> proxy --> Chat-Completions provider

Claude Desktop's "Gateway" mode only emits Anthropic-shaped model names (claude-*)
and hard-validates them, so it cannot be pointed straight at providers whose models
are named differently (MiniMax-M3, glm-5.2, qwen3.7-max, ...). The `/v1/messages`
front end renames the model to the upstream's real id and forwards.

Codex CLI 0.122+ removed `wire_api = "chat"`, so a custom provider must speak the
OpenAI Responses API, which almost no third-party provider serves. The
`/v1/responses` front end accepts Responses, talks Chat Completions upstream, and
streams the result back as Responses events (see codex_bridge.py).

Provider-agnostic. Everything is set in config.json; nothing is hardcoded and no key
is stored on disk (the key is read from the environment variable you name in config).

Run:  python proxy.py [config.json]      (foreground, for a first test)
      pythonw proxy.py                   (Windows, no console window)
Stdlib only -- no pip install.
"""
import datetime
import http.client
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codex_bridge  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "config.json")

with open(CONFIG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

PORT = int(CFG.get("port", 8801))
LOG_PATH = os.path.join(HERE, "proxy.log")


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


class Provider:
    """One provider endpoint. Several routes may share it."""

    def __init__(self, name, spec):
        self.name = name
        self.host = spec["host"]
        self.prefix = spec.get("prefix", "")
        self.scheme = spec.get("scheme", "https")
        self.auth_header = spec.get("auth_header", "x-api-key")
        # "passthrough" forwards the caller's own credentials untouched, which is how
        # a route can reach your real Anthropic subscription through the same proxy.
        self.auth = spec.get("auth", "key")
        self.key_env = spec.get("key_env")
        # macOS Keychain service name. Read only when the environment variable is
        # unset, so Windows and CI keep working through the environment alone.
        self.keychain = spec.get("keychain")
        self.keychain_account = spec.get("keychain_account") or os.environ.get("USER") or ""
        self.extra_body = spec.get("extra_body") or {}
        self._cached_key = None

    @property
    def base(self):
        return f"{self.scheme}://{self.host}{self.prefix}"

    def _from_keychain(self):
        if not self.keychain or sys.platform != "darwin":
            return None
        cmd = ["/usr/bin/security", "find-generic-password", "-s", self.keychain]
        if self.keychain_account:
            cmd += ["-a", self.keychain_account]
        cmd.append("-w")
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as e:
            log(f"keychain lookup failed for '{self.keychain}': {e}")
            return None
        if done.returncode != 0:
            log(f"keychain item '{self.keychain}' not found: {done.stderr.strip()[:200]}")
            return None
        return done.stdout.rstrip("\n") or None

    @property
    def key(self):
        if self.key_env:
            value = os.environ.get(self.key_env)
            if value:
                return value
        if self._cached_key is None:
            self._cached_key = self._from_keychain()
        return self._cached_key

    def key_problem(self):
        """Return a human-readable reason this provider cannot authenticate, or None.

        Deliberately not fatal. One provider with an unsaved key must not stop the
        others from serving: the failure belongs to the request that needs that
        key, not to the whole process.
        """
        if self.auth == "passthrough":
            return None
        if not self.key_env and not self.keychain:
            return (f"provider '{self.name}' needs a key_env, a keychain, "
                    "or \"auth\": \"passthrough\".")
        if not self.key:
            where = " or ".join(filter(None, [
                f"${self.key_env}" if self.key_env else "",
                f"Keychain service '{self.keychain}'" if self.keychain else "",
            ]))
            return f"no key found for provider '{self.name}' (looked in {where})"
        return None

    def require_key(self):
        problem = self.key_problem()
        if problem:
            print(f"warning: {problem}; routes using it will return 503", file=sys.stderr)
            log(f"startup warning: {problem}")

    def auth_headers(self, incoming):
        if self.auth == "passthrough":
            out = {}
            for header in ("authorization", "x-api-key"):
                value = incoming.get(header)
                if value:
                    out[header] = value
            return out
        if self.auth_header == "authorization":
            return {"authorization": f"Bearer {self.key}"}
        return {self.auth_header: self.key}

    def connect(self, timeout=600):
        cls = (http.client.HTTPSConnection if self.scheme == "https"
               else http.client.HTTPConnection)
        return cls(self.host, timeout=timeout)


class Router:
    """A front end's model map. Each route may name its own provider."""

    def __init__(self, models, default_provider, providers):
        # Keys beginning with "_" are comments, not routes. The example configs use
        # them, so treating one as a route crashes on a perfectly valid file.
        self.models = {k: v for k, v in (models or {}).items()
                       if not k.startswith("_") and isinstance(v, dict)}
        self.default_provider = default_provider
        self.providers = providers
        # Keywords are matched in the order listed; "default" is the fallback.
        self.order = [k for k in self.models if k != "default"]
        for spec in self.models.values():
            self.provider_for(spec).require_key()

    def provider_for(self, spec):
        name = spec.get("provider")
        if not name:
            if self.default_provider is None:
                sys.exit("a route has no \"provider\" and no default upstream is configured.")
            return self.default_provider
        if name not in self.providers:
            sys.exit(f"unknown provider '{name}'. Define it under \"providers\" in config.json.")
        return self.providers[name]

    def route(self, model):
        """Map an incoming model name to (spec, provider).

        Unknown names fall back to `default`. With no `default` the name passes
        through untouched, which is what `codex -m glm-5.2` needs against a
        provider that serves many models.
        """
        lowered = (model or "").lower()
        spec = None
        for keyword in self.order:
            # A route key may list alternatives: "glm|deepseek|kimi".
            if any(part and part.lower() in lowered for part in keyword.split("|")):
                spec = self.models[keyword]
                break
        if spec is None:
            spec = self.models.get("default") or {"name": model, "thinking": None}
        resolved = dict(spec)
        if resolved.get("name") in (None, "passthrough"):
            resolved["name"] = model
        return resolved, self.provider_for(spec)

    def describe(self):
        out = {}
        for name, spec in self.models.items():
            provider = self.provider_for(spec).name
            out[name] = f"{provider}:{spec.get('name') or 'passthrough'}"
        return out


PROVIDERS = {name: Provider(name, spec)
             for name, spec in (CFG.get("providers") or {}).items()
             if not name.startswith("_") and isinstance(spec, dict)}

# Backward compatible: a single `upstream` block becomes the default provider.
DEFAULT_PROVIDER = None
if CFG.get("upstream"):
    DEFAULT_PROVIDER = Provider("upstream", CFG["upstream"])
    PROVIDERS.setdefault("upstream", DEFAULT_PROVIDER)
    DEFAULT_PROVIDER.require_key()
elif len(PROVIDERS) == 1:
    DEFAULT_PROVIDER = next(iter(PROVIDERS.values()))

MESSAGES = Router(CFG.get("models"), DEFAULT_PROVIDER, PROVIDERS)

CODEX = None
if CFG.get("codex"):
    codex_cfg = CFG["codex"]
    codex_default = DEFAULT_PROVIDER
    if codex_cfg.get("host"):
        codex_cfg.setdefault("key_env", DEFAULT_PROVIDER.key_env if DEFAULT_PROVIDER else None)
        codex_default = Provider("codex", codex_cfg)
        PROVIDERS.setdefault("codex", codex_default)
        codex_default.require_key()
    CODEX = Router(codex_cfg.get("models"), codex_default, PROVIDERS)


def is_small_probe(data):
    # Claude Desktop fires tiny permission/auto-mode probes. If a provider spends the
    # whole budget on a reasoning block it returns no decision ("auto mode cannot
    # determine safety"). Force thinking off on those regardless of the model's policy.
    try:
        return 0 < int(data.get("max_tokens") or 0) <= 4096
    except (TypeError, ValueError):
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # -- response helpers ------------------------------------------------
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _begin_chunked(self, status, content_type, extra_headers=()):
        self.send_response(status)
        for key, value in extra_headers:
            self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()

    def _write_chunk(self, data):
        if not data:
            return
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _end_chunked(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    # -- local endpoints -------------------------------------------------
    def _health(self):
        payload = {
            "status": "ok",
            "providers": {name: p.base for name, p in PROVIDERS.items()},
            "models": {name: spec["name"] for name, spec in MESSAGES.models.items()},
            "routes": MESSAGES.describe(),
        }
        if DEFAULT_PROVIDER:
            payload["upstream"] = DEFAULT_PROVIDER.base
        if CODEX:
            payload["codex_routes"] = CODEX.describe()
            payload["codex_models"] = {n: s.get("name") or "passthrough"
                                       for n, s in CODEX.models.items()}
            if CODEX.default_provider:
                payload["codex_upstream"] = CODEX.default_provider.base
        self._send_json(200, payload)

    def _models(self):
        source = CODEX or MESSAGES
        names = sorted({spec.get("name") for spec in source.models.values()
                        if spec.get("name") and spec.get("name") != "passthrough"})
        self._send_json(200, {
            "object": "list",
            "data": [{"id": n, "object": "model", "owned_by": "claudecodex"} for n in names],
        })

    # -- /v1/messages : Anthropic front end, Anthropic upstream ----------
    def _messages(self):
        body = self._read_body()
        model_in = ""
        upstream_model = "-"
        think = "-"
        # Logged so a background probe can be told apart from a typed turn:
        # both carry the same model name, and only the budget distinguishes them.
        budget = "-"
        provider = MESSAGES.default_provider or DEFAULT_PROVIDER

        if body and self.path.startswith("/v1/messages"):
            try:
                data = json.loads(body)
                model_in = data.get("model") or ""
                budget = data.get("max_tokens") or "-"
                spec, provider = MESSAGES.route(model_in)
                upstream_model = spec["name"]
                data["model"] = upstream_model
                if self.path.startswith("/v1/messages/count_tokens"):
                    data.pop("thinking", None)
                    data.pop("max_tokens", None)
                    data.pop("stream", None)
                else:
                    policy = spec.get("thinking")   # "adaptive" | "disabled" | None
                    if policy == "adaptive" and is_small_probe(data):
                        policy = "disabled"
                    think = policy or "none"
                    if policy in ("adaptive", "disabled"):
                        data["thinking"] = {"type": policy}
                    else:
                        data.pop("thinking", None)
                if provider.extra_body:
                    data.update(provider.extra_body)
                body = json.dumps(data).encode()
            except Exception as e:  # noqa: BLE001 -- log and forward untouched
                log(f"body parse skip: {e}")

        if provider is None:
            self._send_json(501, {"error": {
                "type": "not_configured",
                "message": "No provider is configured for /v1/messages.",
            }})
            return
        problem = provider.key_problem()
        if problem:
            log(f"{self.path} model={model_in or '-'} blocked: {problem}")
            self._send_json(503, {"type": "error", "error": {
                "type": "authentication_error",
                "message": f"{problem}. Save it, then restart the proxy.",
            }})
            return

        headers = {
            **provider.auth_headers(self.headers),
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            "Content-Type": "application/json",
            "Accept": self.headers.get("Accept", "*/*"),
            "Content-Length": str(len(body)),
        }
        beta = self.headers.get("anthropic-beta")
        if beta:
            headers["anthropic-beta"] = beta

        conn = provider.connect()
        try:
            conn.request(self.command, provider.prefix + self.path, body=body, headers=headers)
            resp = conn.getresponse()
            content_type = resp.getheader("Content-Type") or ""
            log(f"{self.command} {self.path} model={model_in or '-'} think={think} "
                f"max_tokens={budget} -> {provider.name}:{upstream_model} "
                f"status={resp.status}")

            if "text/event-stream" in content_type:
                # Stream through so Claude renders tokens as they arrive.
                self._begin_chunked(resp.status, content_type)
                while True:
                    block = resp.read(4096)
                    if not block:
                        break
                    self._write_chunk(block)
                self._end_chunked()
                return

            payload = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:  # noqa: BLE001
            log(f"upstream error: {e}")
            self.send_error(502, "upstream error")
        finally:
            conn.close()

    # -- /v1/responses : Codex front end, Chat Completions upstream ------
    def _responses(self):
        if CODEX is None:
            self._send_json(501, {"error": {
                "type": "not_configured",
                "message": "Add a \"codex\" block to config.json to serve /v1/responses. "
                           "See examples/alibaba.json.",
            }})
            return

        raw = self._read_body()
        try:
            req = json.loads(raw or b"{}")
        except ValueError as e:
            self._send_json(400, {"error": {"type": "invalid_request", "message": str(e)}})
            return

        model_in = req.get("model") or ""
        spec, provider = CODEX.route(model_in)
        problem = provider.key_problem()
        if problem:
            log(f"/v1/responses model={model_in or '-'} blocked: {problem}")
            self._send_json(503, {"error": {
                "type": "authentication_error",
                "message": f"{problem}. Save it, then restart the proxy.",
            }})
            return
        upstream_model = spec["name"]
        wants_stream = bool(req.get("stream", True))
        chat_body, custom_names, dropped = codex_bridge.responses_to_chat(
            req, upstream_model, provider.extra_body)
        if dropped:
            log(f"codex: dropped unsupported tools {sorted(set(dropped))}")

        payload = json.dumps(chat_body, ensure_ascii=False).encode()
        headers = {
            **provider.auth_headers(self.headers),
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if wants_stream else "application/json",
            "Content-Length": str(len(payload)),
        }
        path = provider.prefix + "/chat/completions"

        conn = provider.connect()
        state = codex_bridge.ResponsesStream(upstream_model, custom_names)
        try:
            conn.request("POST", path, body=payload, headers=headers)
            resp = conn.getresponse()
            log(f"POST /v1/responses model={model_in or '-'} -> "
                f"{provider.name}:{upstream_model} stream={wants_stream} status={resp.status}")

            if resp.status != 200:
                detail = resp.read()
                try:
                    parsed = json.loads(detail)
                except ValueError:
                    parsed = {"error": {"type": "upstream_error",
                                        "message": detail.decode("utf-8", "replace")[:2000]}}
                self._send_json(resp.status, parsed)
                return

            if not wants_stream:
                body = json.loads(resp.read() or b"{}")
                done = codex_bridge.chat_response_to_stream(body, upstream_model, custom_names)
                self._send_json(200, done.snapshot())
                return

            self._begin_chunked(200, "text/event-stream")
            for event in state.start():
                self._write_chunk(event)

            for data in codex_bridge.iter_sse_data(lambda: resp.read(4096)):
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if isinstance(chunk, dict) and chunk.get("error"):
                    message = chunk["error"]
                    message = message.get("message") if isinstance(message, dict) else str(message)
                    for event in state.fail(message or "upstream error"):
                        self._write_chunk(event)
                    self._end_chunked()
                    return
                for event in state.feed(chunk):
                    self._write_chunk(event)

            for event in state.finish():
                self._write_chunk(event)
            self._end_chunked()
        except Exception as e:  # noqa: BLE001
            log(f"codex upstream error: {e}")
            if state.seq:
                try:
                    for event in state.fail(str(e)):
                        self._write_chunk(event)
                    self._end_chunked()
                except OSError:
                    pass
            else:
                self._send_json(502, {"error": {"type": "upstream_error", "message": str(e)}})
        finally:
            conn.close()

    # -- routing ---------------------------------------------------------
    def do_POST(self):
        if self.path.startswith("/v1/responses"):
            self._responses()
        else:
            self._messages()

    def do_GET(self):
        if self.path == "/health":
            self._health()
        elif self.path.startswith("/v1/models"):
            self._models()
        else:
            self._messages()


if __name__ == "__main__":
    summary = ", ".join(f"{name} -> {p.base}" for name, p in PROVIDERS.items())
    banner = f"claudecodex proxy on 127.0.0.1:{PORT}\n  providers: {summary}"
    banner += f"\n  /v1/messages routes: {MESSAGES.describe()}"
    if CODEX:
        banner += f"\n  /v1/responses routes: {CODEX.describe()}"
    log(f"START :{PORT} providers=[{summary}] (config {os.path.basename(CONFIG_PATH)})")
    print(banner)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
