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


class ProxyHealthTest(unittest.TestCase):
    def test_health_is_local_and_does_not_call_upstream(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name in ("proxy.py", "codex_bridge.py"):
                shutil.copy2(Path(__file__).parents[1] / name, root / name)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            config = {
                "port": port,
                "upstream": {
                    "host": "127.0.0.1:9",
                    "prefix": "/anthropic",
                    "scheme": "http",
                    "auth_header": "x-api-key",
                    "key_env": "CLAUDECODEX_TEST_KEY",
                },
                "models": {
                    "default": {"name": "test-model", "thinking": None}
                },
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            env = {**os.environ, "CLAUDECODEX_TEST_KEY": "not-a-real-key"}
            process = subprocess.Popen(
                [sys.executable, str(root / "proxy.py"), str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            try:
                url = f"http://127.0.0.1:{port}/health"
                for _ in range(40):
                    try:
                        with urllib.request.urlopen(url, timeout=0.2) as response:
                            payload = json.load(response)
                        break
                    except OSError:
                        time.sleep(0.025)
                else:
                    self.fail("proxy health endpoint did not start")
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["models"], {"default": "test-model"})
            finally:
                process.terminate()
                process.wait(timeout=2)


class FakeChatUpstream(http.server.BaseHTTPRequestHandler):
    """Minimal Chat Completions server that streams one text chunk and one tool call."""

    received = {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        FakeChatUpstream.received.clear()
        FakeChatUpstream.received.update(json.loads(self.rfile.read(length) or b"{}"))
        FakeChatUpstream.received["_auth"] = self.headers.get("authorization", "")
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "planning"}}]},
            {"choices": [{"delta": {"content": "hello "}}]},
            {"choices": [{"delta": {"content": "world"}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_x",
                 "function": {"name": "shell", "arguments": "{\"cmd\":\"ls\"}"}}]}}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class CodexResponsesTest(unittest.TestCase):
    """Prove the /v1/responses front end Codex requires, without a paid request."""

    def setUp(self):
        self.upstream_port = _free_port()
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.upstream_port), FakeChatUpstream)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, self.root / name)
        self.port = _free_port()
        config = {
            "port": self.port,
            "upstream": {"host": "127.0.0.1:9", "prefix": "/anthropic", "scheme": "http",
                         "auth_header": "x-api-key", "key_env": "CLAUDECODEX_TEST_KEY"},
            "models": {"default": {"name": "test-model", "thinking": None}},
            "codex": {"host": f"127.0.0.1:{self.upstream_port}", "prefix": "", "scheme": "http",
                      "auth_header": "authorization", "key_env": "CLAUDECODEX_TEST_KEY",
                      "models": {"gpt-": {"name": "qwen3.7-max"}}},
        }
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(config))
        self.process = subprocess.Popen(
            [sys.executable, str(self.root / "proxy.py"), str(config_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "CLAUDECODEX_TEST_KEY": "not-a-real-key"})
        self.addCleanup(self._stop)
        self._wait_ready()

    def _stop(self):
        self.process.terminate()
        self.process.wait(timeout=5)

    def _wait_ready(self):
        for _ in range(80):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/health", timeout=0.2):
                    return
            except OSError:
                time.sleep(0.025)
        self.fail("proxy did not start")

    def _post_responses(self, body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/responses",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.headers.get("Content-Type"), "text/event-stream")
            raw = response.read().decode()
        return [json.loads(line[5:].strip()) for line in raw.split("\n")
                if line.startswith("data:")]

    def test_codex_request_streams_back_as_responses_events(self):
        events = self._post_responses({
            "model": "gpt-5.6-sol",
            "instructions": "be terse",
            "input": [{"type": "message", "role": "user",
                       "content": [{"type": "input_text", "text": "hi"}]}],
            "tools": [{"type": "function", "name": "shell",
                       "parameters": {"type": "object", "properties": {}}}],
            "stream": True,
        })
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "response.created")
        self.assertEqual(types[-1], "response.completed")
        self.assertIn("response.output_text.delta", types)
        self.assertIn("response.reasoning_summary_text.delta", types)

        completed = events[-1]["response"]
        self.assertEqual(completed["model"], "qwen3.7-max")
        self.assertEqual(completed["usage"]["input_tokens"], 7)
        kinds = [item["type"] for item in completed["output"]]
        self.assertEqual(kinds, ["reasoning", "message", "function_call"])
        message = completed["output"][1]
        self.assertEqual(message["content"][0]["text"], "hello world")
        self.assertEqual(completed["output"][2]["call_id"], "call_x")

    def test_upstream_receives_translated_chat_request_and_bearer_key(self):
        self._post_responses({
            "model": "gpt-5.6-sol",
            "instructions": "be terse",
            "input": [{"type": "message", "role": "user",
                       "content": [{"type": "input_text", "text": "hi"}]}],
            "stream": True,
        })
        sent = FakeChatUpstream.received
        self.assertEqual(sent["model"], "qwen3.7-max")
        self.assertEqual(sent["messages"],
                         [{"role": "system", "content": "be terse"},
                          {"role": "user", "content": "hi"}])
        self.assertEqual(sent["stream_options"], {"include_usage": True})
        self.assertEqual(sent["_auth"], "Bearer not-a-real-key")

    def test_health_reports_both_front_ends(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
            payload = json.load(r)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["codex_upstream"].startswith("http://127.0.0.1:"))


class CodexNotConfiguredTest(unittest.TestCase):
    def test_responses_returns_501_without_a_codex_block(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("proxy.py", "codex_bridge.py"):
            shutil.copy2(Path(__file__).parents[1] / name, root / name)
        port = _free_port()
        config_path = root / "config.json"
        config_path.write_text(json.dumps({
            "port": port,
            "upstream": {"host": "127.0.0.1:9", "prefix": "", "scheme": "http",
                         "auth_header": "x-api-key", "key_env": "CLAUDECODEX_TEST_KEY"},
            "models": {"default": {"name": "test-model", "thinking": None}},
        }))
        process = subprocess.Popen(
            [sys.executable, str(root / "proxy.py"), str(config_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "CLAUDECODEX_TEST_KEY": "not-a-real-key"})
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
            f"http://127.0.0.1:{port}/v1/responses", data=b"{}",
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 501)


if __name__ == "__main__":
    unittest.main()
