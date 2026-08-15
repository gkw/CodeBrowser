from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import server


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True)
    return result.stdout


class DummyServer:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.read_only = False

    def safe_path(self, relative: str) -> Path:
        candidate = (self.root / relative.lstrip("/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError
        return candidate


class LoopManagerTests(unittest.TestCase):
    def test_unittest_project_uses_stdlib_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            self.assertEqual(
                server.detected_test_command(root),
                ["python3", "-m", "unittest", "discover", "-s", "tests"],
            )

    def test_non_git_project_gets_safe_local_initial_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("value = 1\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            data = root / "data"
            data.mkdir()
            (data / "runtime.db").write_bytes(b"private")

            repository = server.initialize_local_repository(root)

            self.assertEqual(repository, root.resolve())
            self.assertTrue((root / ".git").is_dir())
            self.assertIn("Initial local snapshot", git(root, "log", "-1", "--pretty=%s"))
            self.assertEqual(git(root, "ls-files").splitlines(), ["sample.py"])
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_two_round_loop_applies_commits_and_stops_when_no_changes_remain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.py"
            source.write_text("def answer():\n    return 1\n", encoding="utf-8")
            git(root, "init")
            git(root, "config", "user.name", "Loop Test")
            git(root, "config", "user.email", "loop@example.invalid")
            git(root, "add", "sample.py")
            git(root, "commit", "-m", "Initial")
            loop_state = root / ".git" / "loop-state.json"
            integration_calls = 0

            def fake_model(_host: str, _model: str, messages: list[dict[str, str]], *, json_format: bool = False) -> str:
                nonlocal integration_calls
                if not json_format:
                    return "`sample.py` should return the stable value 2."
                integration_calls += 1
                if integration_calls > 1:
                    return json.dumps({"summary": "No further safe changes", "changes": []})
                prompt = messages[-1]["content"]
                digest = re.search(r"SHA256: ([0-9a-f]{64})", prompt).group(1)
                return json.dumps({
                    "summary": "Update the sample implementation",
                    "changes": [{
                        "path": "invented/subdirectory/sample.py",
                        "originalSha256": digest,
                        "newContent": "def answer():\n    return 2\n",
                        "reason": "Apply the agreed improvement",
                    }],
                })

            with (
                patch.object(server, "LOOP_STATE_PATH", loop_state),
                patch.object(server, "discover_ollama_models", return_value=("mock://ollama", ["model-a", "model-b", "model-c"])),
                patch.object(server, "call_ollama_text", side_effect=fake_model),
                patch.object(server, "detected_test_command", return_value=None),
            ):
                manager = server.LoopManager(DummyServer(root))
                manager.start({"path": "", "targetType": "project", "rounds": 3, "models": ["model-a", "model-b", "model-c"]})
                deadline = time.time() + 10
                while manager.status().get("status") in {"queued", "running"} and time.time() < deadline:
                    time.sleep(0.05)
                result = manager.status()

            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(result["rounds"]), 2)
            self.assertEqual(result["rounds"][0]["status"], "complete")
            self.assertEqual(result["rounds"][0]["changes"][0]["path"], "sample.py")
            self.assertEqual(result["rounds"][0]["changes"][0]["requestedPath"], "invented/subdirectory/sample.py")
            self.assertEqual(result["rounds"][0]["tests"]["status"], "skipped")
            self.assertEqual(result["rounds"][1]["status"], "no_changes")
            self.assertEqual(source.read_text(encoding="utf-8"), "def answer():\n    return 2\n")
            self.assertTrue(git(root, "branch", "--show-current").startswith("ollama-loop/"))
            self.assertIn("Ollama loop round 1", git(root, "log", "-1", "--pretty=%s"))
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_dirty_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.py"
            source.write_text("value = 1\n", encoding="utf-8")
            git(root, "init")
            git(root, "config", "user.name", "Loop Test")
            git(root, "config", "user.email", "loop@example.invalid")
            git(root, "add", "sample.py")
            git(root, "commit", "-m", "Initial")
            source.write_text("value = 2\n", encoding="utf-8")
            with patch.object(server, "LOOP_STATE_PATH", root / ".git" / "loop-state.json"):
                manager = server.LoopManager(DummyServer(root))
                with self.assertRaisesRegex(ValueError, "clean"):
                    manager.start({"path": "", "targetType": "project", "rounds": 3, "models": []})

    def test_invalid_integrator_output_retries_with_next_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.py"
            source.write_text("value = 1\n", encoding="utf-8")
            git(root, "init")
            git(root, "config", "user.name", "Loop Test")
            git(root, "config", "user.email", "loop@example.invalid")
            git(root, "add", "sample.py")
            git(root, "commit", "-m", "Initial")

            def fake_model(_host: str, model: str, messages: list[dict[str, str]], *, json_format: bool = False) -> str:
                if not json_format:
                    return "Update the value."
                digest = re.search(r"SHA256: ([0-9a-f]{64})", messages[-1]["content"]).group(1)
                content = "+value = 2\n+broken = True\n+third = True\n" if model == "model-a" else "value = 2\n"
                return json.dumps({
                    "summary": "Retry succeeded",
                    "changes": [{"path": "sample.py", "originalSha256": digest, "newContent": content, "reason": "Apply valid output"}],
                })

            with (
                patch.object(server, "LOOP_STATE_PATH", root / ".git" / "loop-state.json"),
                patch.object(server, "discover_ollama_models", return_value=("mock://ollama", ["model-a", "model-b"])),
                patch.object(server, "call_ollama_text", side_effect=fake_model),
                patch.object(server, "detected_test_command", return_value=None),
            ):
                manager = server.LoopManager(DummyServer(root))
                manager.start({"path": "", "targetType": "project", "rounds": 1, "models": ["model-a", "model-b"], "language": "en"})
                deadline = time.time() + 10
                while manager.status().get("status") in {"queued", "running"} and time.time() < deadline:
                    time.sleep(0.05)
                result = manager.status()

            self.assertEqual(result["status"], "completed")
            attempts = result["rounds"][0]["integrationAttempts"]
            self.assertEqual([(item["model"], item["status"]) for item in attempts], [("model-a", "failed"), ("model-b", "complete")])
            self.assertEqual(source.read_text(encoding="utf-8"), "value = 2\n")
            self.assertIn("Ollama loop round 1", git(root, "log", "-1", "--pretty=%s"))

    def test_patch_shaped_python_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "差分記号"):
            server.validate_generated_source("sample.py", '"""doc"""\n+value = 1\n+other = 2\n+more = 3\n')

    def test_failed_test_rolls_back_without_loop_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.py"
            original = "def answer():\n    return 1\n"
            source.write_text(original, encoding="utf-8")
            git(root, "init")
            git(root, "config", "user.name", "Loop Test")
            git(root, "config", "user.email", "loop@example.invalid")
            git(root, "add", "sample.py")
            git(root, "commit", "-m", "Initial")

            def fake_model(_host: str, _model: str, messages: list[dict[str, str]], *, json_format: bool = False) -> str:
                if not json_format:
                    return "Change the return value."
                digest = re.search(r"SHA256: ([0-9a-f]{64})", messages[-1]["content"]).group(1)
                return json.dumps({
                    "summary": "Change it",
                    "changes": [{
                        "path": "sample.py",
                        "originalSha256": digest,
                        "newContent": "def answer():\n    return 2\n",
                        "reason": "test rollback",
                    }],
                })

            with (
                patch.object(server, "LOOP_STATE_PATH", root / ".git" / "loop-state.json"),
                patch.object(server, "discover_ollama_models", return_value=("mock://ollama", ["model-a"])),
                patch.object(server, "call_ollama_text", side_effect=fake_model),
                patch.object(server, "detected_test_command", return_value=[sys.executable, "-c", "raise SystemExit(1)"]),
            ):
                manager = server.LoopManager(DummyServer(root))
                manager.start({"path": "", "targetType": "project", "rounds": 1, "models": ["model-a"], "language": "en"})
                deadline = time.time() + 10
                while manager.status().get("status") in {"queued", "running"} and time.time() < deadline:
                    time.sleep(0.05)
                result = manager.status()

            self.assertEqual(result["status"], "failed")
            self.assertIn("rolled back", result["message"])
            self.assertEqual(result["rounds"][0]["status"], "failed")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertEqual(git(root, "rev-list", "--count", "HEAD").strip(), "1")
            self.assertEqual(git(root, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
