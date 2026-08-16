from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from provider_plugins import PluginError, PluginManifest, PluginRegistry, ProviderPluginClient


class FakeOllamaHandler(BaseHTTPRequestHandler):
    authorization = ""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_value(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        type(self).authorization = self.headers.get("Authorization", "")
        self.send_value({"models": [{"name": "model-a"}, {"name": "model-b"}]})

    def do_POST(self) -> None:
        type(self).authorization = self.headers.get("Authorization", "")
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.send_value({
            "message": {"content": f"used {payload['model']}"},
            "prompt_eval_count": 12,
            "eval_count": 7,
        })


class ProviderPluginTests(unittest.TestCase):
    def create_plugin(self, directory: Path, *, plugin_id: str = "test-provider", entrypoint: str = "plugin.py") -> Path:
        plugin_directory = directory / plugin_id
        plugin_directory.mkdir()
        (plugin_directory / "plugin.py").write_text(
            """import json, os, sys
request = json.loads(sys.stdin.readline())
if request['method'] == 'models.list':
    result = {'models': ['model-a'], 'allowed': os.environ.get('PLUGIN_ALLOWED'), 'hidden': os.environ.get('SECRET_NOT_ALLOWED')}
else:
    result = {'content': 'answer', 'usage': {'promptTokens': 3, 'outputTokens': 2}}
print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}))
""",
            encoding="utf-8",
        )
        manifest = plugin_directory / "code-browser-plugin.json"
        manifest.write_text(json.dumps({
            "id": plugin_id,
            "name": "Test provider",
            "version": "1.0.0",
            "type": "provider",
            "protocolVersion": 1,
            "entrypoint": entrypoint,
            "environment": ["PLUGIN_ALLOWED"],
        }), encoding="utf-8")
        return manifest

    def test_plugin_runs_out_of_process_with_minimal_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = PluginManifest.load(self.create_plugin(root))
            client = ProviderPluginClient(manifest)
            with patch.dict(os.environ, {"PLUGIN_ALLOWED": "yes", "SECRET_NOT_ALLOWED": "no"}, clear=False):
                raw = client._call("models.list", {})
                models = client.list_models()
            self.assertEqual(raw["allowed"], "yes")
            self.assertIsNone(raw["hidden"])
            self.assertEqual(models, ["model-a"])
            result = client.infer(
                request_id="request-1", operation="summary", model="model-a",
                messages=[{"role": "user", "content": "source"}],
            )
            self.assertEqual(result, {"content": "answer", "usage": {"promptTokens": 3, "outputTokens": 2}})

    def test_manifest_rejects_entrypoint_escape_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self.create_plugin(root, entrypoint="../outside.py")
            (root / "outside.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(PluginError, "escapes"):
                PluginManifest.load(manifest_path)

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            self.create_plugin(Path(first), plugin_id="duplicate-provider")
            self.create_plugin(Path(second), plugin_id="duplicate-provider")
            with self.assertRaisesRegex(PluginError, "Duplicate"):
                PluginRegistry.discover([Path(first), Path(second)])

    def test_reference_ollama_plugin_end_to_end(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            plugin_path = Path(__file__).resolve().parents[1] / "plugins/providers/ollama-compatible/code-browser-plugin.json"
            client = ProviderPluginClient(PluginManifest.load(plugin_path))
            environment = {
                "OLLAMA_PLUGIN_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "OLLAMA_PLUGIN_API_KEY": "test-key",
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertEqual(client.list_models(), ["model-a", "model-b"])
                result = client.infer(
                    request_id="request-2", operation="summary", model="model-a",
                    messages=[{"role": "user", "content": "source"}], maximum_output_tokens=50,
                )
            self.assertEqual(FakeOllamaHandler.authorization, "Bearer test-key")
            self.assertEqual(result["content"], "used model-a")
            self.assertEqual(result["usage"], {"promptTokens": 12, "outputTokens": 7})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
