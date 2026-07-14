"""Anthropic-format model-name proxy for Claude Desktop / Claude Code.

Claude Desktop's "Gateway" (third-party inference) mode only emits Anthropic-shaped
model names (claude-*) and hard-validates them, so it cannot be pointed straight at
providers whose models are named differently (MiniMax-M3, glm-4.7, kimi-k2, ...) even
though they all speak the Anthropic Messages format. This proxy renames the model to
the upstream's real id and forwards, which is the one missing piece:

    Claude Desktop --model=claude-*--> proxy :PORT --model=<upstream>--> provider

Provider-agnostic. Everything is set in config.json; nothing is hardcoded and no key is
stored on disk (the key is read from the environment variable you name in config).

Run:  python proxy.py [config.json]      (foreground, for a first test)
      pythonw proxy.py                   (Windows, no console window)
Stdlib only -- no pip install.
"""
import datetime
import http.client
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "config.json")

with open(CONFIG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

PORT = int(CFG.get("port", 8801))
UP = CFG["upstream"]                       # {host, prefix, key_env, scheme?}
HOST = UP["host"]
PREFIX = UP.get("prefix", "")
SCHEME = UP.get("scheme", "https")         # https (default) or http, for local gateways
KEY_ENV = UP["key_env"]
KEY = os.environ.get(KEY_ENV)
if not KEY:
    sys.exit(f"{KEY_ENV} is not set. Set it (see README) and restart the proxy.")

# models: keyword found in the incoming claude-* name -> {name, thinking}
# "default" is the fallback. Keywords are matched in the order listed.
MODELS = CFG["models"]
ORDER = [k for k in MODELS if k != "default"]
LOG_PATH = os.path.join(HERE, "proxy.log")
AUTH_HEADER = UP.get("auth_header", "x-api-key")   # x-api-key (Anthropic) or authorization


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def route(model):
    ml = model.lower()
    for kw in ORDER:
        if kw.lower() in ml:
            return MODELS[kw]
    return MODELS["default"]


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

    def _proxy(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        model_in = ""
        upstream_model = "-"
        think = "-"

        if body and self.path.startswith("/v1/messages"):
            try:
                data = json.loads(body)
                model_in = data.get("model") or ""
                spec = route(model_in)
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
                body = json.dumps(data).encode()
            except Exception as e:  # noqa: BLE001 -- log and forward untouched
                log(f"body parse skip: {e}")

        auth = {"authorization": f"Bearer {KEY}"} if AUTH_HEADER == "authorization" else {"x-api-key": KEY}
        headers = {
            **auth,
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            "Content-Type": "application/json",
            "Accept": self.headers.get("Accept", "*/*"),
            "Content-Length": str(len(body)),
        }
        Conn = http.client.HTTPSConnection if SCHEME == "https" else http.client.HTTPConnection
        conn = Conn(HOST, timeout=600)
        try:
            conn.request(self.command, PREFIX + self.path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            log(f"{self.command} {self.path} model={model_in or '-'} think={think} "
                f"-> {upstream_model} status={resp.status}")
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

    do_POST = _proxy
    do_GET = _proxy


if __name__ == "__main__":
    log(f"START :{PORT} -> {SCHEME}://{HOST}{PREFIX}  (config {os.path.basename(CONFIG_PATH)})")
    print(f"gateway proxy on 127.0.0.1:{PORT} -> {SCHEME}://{HOST}{PREFIX}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
