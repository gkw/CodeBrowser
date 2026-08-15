from __future__ import annotations

import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server


class FileUtilityTests(unittest.TestCase):
    def test_binary_detection_handles_nulls_controls_and_text(self) -> None:
        self.assertTrue(server.is_probably_binary(b"PNG\x00\x01\x02"))
        self.assertTrue(server.is_probably_binary(bytes(range(1, 16)) * 20))
        self.assertFalse(server.is_probably_binary("日本語のソース\nvalue = 1\n".encode("utf-8")))
        self.assertFalse(server.is_probably_binary(b""))

    def test_atomic_json_write_replaces_complete_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            server.atomic_write_json(path, {"version": 1}, ".state.")
            server.atomic_write_json(path, {"version": 2, "items": [1, 2]}, ".state.")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2, "items": [1, 2]})
            self.assertEqual(list(Path(directory).glob(".state.*")), [])

    def test_ollama_probe_cache_is_invalidated_when_hosts_change(self) -> None:
        old_cache = server._ollama_probe_cache
        server._ollama_probe_cache = None
        try:
            with patch.object(server, "urlopen", side_effect=lambda *_args, **_kwargs: io.StringIO('{"models": [{"name": "model-a"}]}')) as request:
                environment = {key: value for key, value in os.environ.items() if key != "OLLAMA_API_KEY"}
                environment["OLLAMA_HOSTS"] = "http://host-one.invalid:11434"
                with patch.dict(os.environ, environment, clear=True):
                    self.assertEqual(server.probe_ollama_models()[0], "http://host-one.invalid:11434")
                    os.environ["OLLAMA_HOSTS"] = "http://host-two.invalid:11434"
                    self.assertEqual(server.probe_ollama_models()[0], "http://host-two.invalid:11434")
            self.assertEqual(request.call_count, 2)
        finally:
            server._ollama_probe_cache = old_cache


if __name__ == "__main__":
    unittest.main()
