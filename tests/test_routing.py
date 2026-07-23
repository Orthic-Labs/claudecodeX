"""Routing rules, exercised through a real proxy process.

These assert the multi-provider promise: one front end can fan out to several
providers, and a route can forward the caller's own credentials instead of a
stored key.
"""
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class RecordingUpstream(http.server.BaseHTTPRequestHandler):
    """Answers both Anthropic Messages and Chat Completions, and records the call."""

    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        RecordingUpstream.calls.append({
            "path": self.path,
            "model": body.get("model"),
            "thinking": body.get("thinking"),
            "authorization": self.headers.get("authorization"),
            "x-api-key": self.headers.get("x-api-key"),
        })
        payload = json.dumps({
            "id": "m1", "type": "message", "role": "assistant",
            "model": body.get("model"),
            "content": [{"type": "text", "text": "ok"}],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class MultiProviderRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RecordingUpstream.calls = []
        cls.up_a = _free_port()
        cls.up_b = _free_port()
        cls.servers = []
        for port in (cls.up_a, cls.up_b):
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), RecordingUpstream)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers.append(server)

        cls.root = Path(tempfile.mkdtemp())
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, cls.root / name)
        cls.port = _free_port()
        config = {
            "port": cls.port,
            "providers": {
                "alpha": {"host": f"127.0.0.1:{cls.up_a}", "prefix": "", "scheme": "http",
                          "auth_header": "x-api-key", "key_env": "CLAUDECODEX_KEY_A"},
                "beta": {"host": f"127.0.0.1:{cls.up_b}", "prefix": "", "scheme": "http",
                         "auth_header": "authorization", "key_env": "CLAUDECODEX_KEY_B"},
                "mine": {"host": f"127.0.0.1:{cls.up_a}", "prefix": "", "scheme": "http",
                         "auth": "passthrough"},
            },
            "models": {
                "fable": {"provider": "alpha", "name": "flagship-model", "thinking": "enabled"},
                "haiku": {"provider": "alpha", "name": "small-model", "thinking": "disabled"},
                "sonnet": {"provider": "beta", "name": "big-model", "thinking": "adaptive"},
                "default": {"provider": "mine", "name": "passthrough"},
            },
            "codex": {"models": {
                "glm|deepseek": {"provider": "beta", "name": "passthrough"},
                "default": {"provider": "alpha", "name": "fallback-model"},
            }},
        }
        (cls.root / "config.json").write_text(json.dumps(config))
        cls.process = subprocess.Popen(
            [sys.executable, str(cls.root / "proxy.py"), str(cls.root / "config.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "CLAUDECODEX_KEY_A": "key-a", "CLAUDECODEX_KEY_B": "key-b"})
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=0.2):
                    break
            except OSError:
                time.sleep(0.025)
        else:
            raise AssertionError("proxy did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def _messages(self, model, headers=None, max_tokens=16):
        RecordingUpstream.calls.clear()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/messages",
            data=json.dumps({"model": model, "max_tokens": max_tokens,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(request, timeout=5) as response:
            json.load(response)
        return RecordingUpstream.calls[-1]

    def _responses(self, model):
        RecordingUpstream.calls.clear()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/responses",
            data=json.dumps({"model": model, "input": [], "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            json.load(response)
        return RecordingUpstream.calls[-1]

    def test_two_providers_serve_one_claude_front_end(self):
        haiku = self._messages("claude-haiku-4-5-20251001")
        self.assertEqual(haiku["model"], "small-model")
        self.assertEqual(haiku["x-api-key"], "key-a")

        sonnet = self._messages("claude-sonnet-5")
        self.assertEqual(sonnet["model"], "big-model")
        self.assertEqual(sonnet["authorization"], "Bearer key-b")

    def test_enabled_thinking_reaches_upstream(self):
        fable = self._messages("claude-fable-5", max_tokens=128)
        self.assertEqual(fable["model"], "flagship-model")
        self.assertEqual(fable["thinking"], {"type": "enabled"})

    def test_passthrough_route_forwards_the_callers_own_credentials(self):
        call = self._messages("claude-opus-4-8",
                              {"authorization": "Bearer sk-ant-caller-token"})
        # The model name is untouched and the proxy's own keys are never substituted.
        self.assertEqual(call["model"], "claude-opus-4-8")
        self.assertEqual(call["authorization"], "Bearer sk-ant-caller-token")
        self.assertIsNone(call["x-api-key"])

    def test_codex_routes_by_model_family_across_providers(self):
        glm = self._responses("glm-5.2")
        self.assertEqual(glm["model"], "glm-5.2")
        self.assertEqual(glm["path"], "/chat/completions")
        self.assertEqual(glm["authorization"], "Bearer key-b")

        deepseek = self._responses("deepseek-v4-pro")
        self.assertEqual(deepseek["model"], "deepseek-v4-pro")

        other = self._responses("gpt-5.6-sol")
        self.assertEqual(other["model"], "fallback-model")
        self.assertEqual(other["x-api-key"], "key-a")

    def test_health_lists_every_provider_and_route(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
            payload = json.load(r)
        self.assertEqual(set(payload["providers"]), {"alpha", "beta", "mine"})
        self.assertEqual(payload["routes"]["haiku"], "alpha:small-model")
        self.assertEqual(payload["routes"]["sonnet"], "beta:big-model")
        self.assertEqual(payload["codex_routes"]["glm|deepseek"], "beta:passthrough")


class ShippedExamplesTest(unittest.TestCase):
    """Every example in examples/ must actually load.

    The comment keys these files use are valid JSON but are not routes, so the
    parser has to skip them. A shipped example that crashes the proxy is a bug.
    """

    def test_each_example_config_starts_the_proxy(self):
        root = Path(__file__).parents[1]
        examples = sorted((root / "examples").glob("*.json"))
        self.assertTrue(examples, "no example configs found")
        for example in examples:
            with self.subTest(example=example.name):
                work = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, work, True)
                for name in ("proxy.py", "codex_bridge.py"):
                    shutil.copy2(root / name, work / name)
                config = json.loads(example.read_text())
                config["port"] = _free_port()
                # Point every provider at a dead local port: this asserts the file
                # parses and every route resolves, without any network call.
                for spec in config.get("providers", {}).values():
                    if isinstance(spec, dict):
                        spec.update({"host": "127.0.0.1:9", "scheme": "http"})
                        spec.pop("keychain", None)
                        spec["key_env"] = "ANYCLAUDE_EXAMPLE_KEY"
                for block in ("upstream", "codex"):
                    spec = config.get(block)
                    if isinstance(spec, dict) and spec.get("host"):
                        spec.update({"host": "127.0.0.1:9", "scheme": "http"})
                        spec.pop("keychain", None)
                        spec["key_env"] = "ANYCLAUDE_EXAMPLE_KEY"
                (work / "config.json").write_text(json.dumps(config))
                process = subprocess.Popen(
                    [sys.executable, str(work / "proxy.py"), str(work / "config.json")],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env={**os.environ, "ANYCLAUDE_EXAMPLE_KEY": "k"})
                self.addCleanup(lambda p=process: (p.terminate(), p.wait(timeout=5)))
                time.sleep(1.2)
                if process.poll() is not None:
                    self.fail(f"{example.name} failed to start:\n{process.stderr.read()}")


class ConfigValidationTest(unittest.TestCase):
    def _start(self, config, env=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        (root / "config.json").write_text(json.dumps(config))
        return subprocess.run(
            [sys.executable, str(root / "proxy.py"), str(root / "config.json")],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, **(env or {})})

    def test_unknown_provider_name_fails_loudly(self):
        result = self._start({
            "port": _free_port(),
            "providers": {"alpha": {"host": "127.0.0.1:9", "scheme": "http",
                                    "key_env": "CLAUDECODEX_KEY_A"}},
            "models": {"default": {"provider": "typo", "name": "m"}},
        }, {"CLAUDECODEX_KEY_A": "k"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown provider 'typo'", result.stderr)

    def test_missing_key_warns_but_does_not_stop_the_proxy(self):
        # One unsaved key must not take down providers that are configured.
        port = _free_port()
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        (root / "config.json").write_text(json.dumps({
            "port": port,
            "providers": {"alpha": {"host": "127.0.0.1:9", "scheme": "http",
                                    "key_env": "CLAUDECODEX_ABSENT"}},
            "models": {"default": {"provider": "alpha", "name": "m"}},
        }))
        process = subprocess.Popen(
            [sys.executable, str(root / "proxy.py"), str(root / "config.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (process.terminate(), process.wait(timeout=5)))
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2):
                    break
            except OSError:
                time.sleep(0.025)
        else:
            self.fail("proxy exited instead of warning about the missing key")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/messages",
            data=json.dumps({"model": "claude-opus-4-8", "max_tokens": 8,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 503)
        detail = json.loads(ctx.exception.read())["error"]["message"]
        self.assertIn("$CLAUDECODEX_ABSENT", detail)
        self.assertIn("provider 'alpha'", detail)

    def test_unused_provider_does_not_require_a_key(self):
        # Only routed providers are required, so one config can list every provider
        # you own without forcing every key to be present.
        config = {
            "port": _free_port(),
            "providers": {
                "used": {"host": "127.0.0.1:9", "scheme": "http", "key_env": "CLAUDECODEX_KEY_A"},
                "unused": {"host": "127.0.0.1:9", "scheme": "http", "key_env": "CLAUDECODEX_ABSENT"},
            },
            "models": {"default": {"provider": "used", "name": "m"}},
        }
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        (root / "config.json").write_text(json.dumps(config))
        process = subprocess.Popen(
            [sys.executable, str(root / "proxy.py"), str(root / "config.json")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "CLAUDECODEX_KEY_A": "k"})
        self.addCleanup(lambda: (process.terminate(), process.wait(timeout=5)))
        time.sleep(1.0)
        self.assertIsNone(process.poll(), "proxy exited despite the unused provider being routed away")


@unittest.skipUnless(sys.platform == "darwin", "macOS Keychain only")
class KeychainKeyTest(unittest.TestCase):
    """The proxy reads a provider key from the login Keychain on macOS."""

    SERVICE = "CLAUDECODEX_UNITTEST_KEY"
    SECRET = "keychain-secret-value"

    @classmethod
    def setUpClass(cls):
        cls.account = os.environ.get("USER") or "claudecodex-test"
        subprocess.run(["/usr/bin/security", "add-generic-password", "-U",
                        "-a", cls.account, "-s", cls.SERVICE,
                        "-T", "/usr/bin/security", "-w", cls.SECRET],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["/usr/bin/security", "delete-generic-password",
                        "-a", cls.account, "-s", cls.SERVICE], capture_output=True)

    def _call(self, provider_spec, env=None):
        RecordingUpstream.calls.clear()
        port = _free_port()
        upstream_port = _free_port()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", upstream_port), RecordingUpstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        spec = {"host": f"127.0.0.1:{upstream_port}", "prefix": "", "scheme": "http",
                "auth_header": "x-api-key", **provider_spec}
        (root / "config.json").write_text(json.dumps({
            "port": port,
            "providers": {"vault": spec},
            "models": {"default": {"provider": "vault", "name": "m"}},
        }))
        clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODEX_VAULT_KEY"}
        process = subprocess.Popen(
            [sys.executable, str(root / "proxy.py"), str(root / "config.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**clean, **(env or {})})
        self.addCleanup(lambda: (process.terminate(), process.wait(timeout=5)))
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2):
                    break
            except OSError:
                time.sleep(0.025)
        else:
            self.fail("proxy did not start")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/messages",
            data=json.dumps({"model": "claude-opus-4-8", "max_tokens": 8,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            json.load(response)
        return RecordingUpstream.calls[-1]

    def test_key_is_read_from_the_keychain(self):
        call = self._call({"keychain": self.SERVICE})
        self.assertEqual(call["x-api-key"], self.SECRET)

    def test_environment_variable_wins_over_the_keychain(self):
        # One config works on both machines: Windows sets the variable, macOS does not.
        call = self._call({"keychain": self.SERVICE, "key_env": "CLAUDECODEX_VAULT_KEY"},
                          {"CLAUDECODEX_VAULT_KEY": "env-wins"})
        self.assertEqual(call["x-api-key"], "env-wins")

    def test_keychain_falls_back_when_the_variable_is_absent(self):
        call = self._call({"keychain": self.SERVICE, "key_env": "CLAUDECODEX_VAULT_KEY"})
        self.assertEqual(call["x-api-key"], self.SECRET)

    def test_missing_keychain_item_names_both_places_it_looked(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        (root / "config.json").write_text(json.dumps({
            "port": _free_port(),
            "providers": {"vault": {"host": "127.0.0.1:9", "scheme": "http",
                                    "keychain": "CLAUDECODEX_NO_SUCH_ITEM",
                                    "key_env": "CLAUDECODEX_NO_SUCH_VAR"}},
            "models": {"default": {"provider": "vault", "name": "m"}},
        }))
        # The proxy stays up and warns; the warning must name both lookups so the
        # fix is obvious without reading the config.
        process = subprocess.Popen(
            [sys.executable, str(root / "proxy.py"), str(root / "config.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (process.terminate(), process.wait(timeout=5)))
        time.sleep(1.2)
        self.assertIsNone(process.poll(), "proxy exited on a missing key")
        process.terminate()
        stderr = process.communicate(timeout=5)[1]
        self.assertIn("$CLAUDECODEX_NO_SUCH_VAR", stderr)
        self.assertIn("CLAUDECODEX_NO_SUCH_ITEM", stderr)


if __name__ == "__main__":
    unittest.main()
