import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


class ProxyHealthTest(unittest.TestCase):
    def test_health_is_local_and_does_not_call_upstream(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            shutil.copy2(Path(__file__).parents[1] / "proxy.py", root / "proxy.py")
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
                    "key_env": "ANYCLAUDE_TEST_KEY",
                },
                "models": {
                    "default": {"name": "test-model", "thinking": None}
                },
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            env = {**os.environ, "ANYCLAUDE_TEST_KEY": "not-a-real-key"}
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


if __name__ == "__main__":
    unittest.main()
