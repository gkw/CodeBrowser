#!/usr/bin/env python3
"""Local code browser and guarded source editor with Ollama-powered explanations."""

from __future__ import annotations

import argparse
import ast
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = (APP_DIR / "static").resolve()
MCP_STATE_PATH = APP_DIR / ".code-browser-mcp-state.json"
LOOP_STATE_PATH = APP_DIR / ".code-browser-loop-state.json"
MAX_FILE_BYTES = 1_500_000
IGNORED_NAMES = {
    ".git", ".svn", ".hg", ".DS_Store", "node_modules", "__pycache__",
    ".venv", "venv", "dist", "build", ".next", ".cache", "coverage",
}
OLLAMA_HOSTS = [
    "http://localhost:11434",
]
OLLAMA_CLOUD_HOST = "https://ollama.com"
LOCAL_CLOUD_SUFFIX = ":cloud"
PAID_CLOUD_MODELS = {"kimi-k3"}
LOOP_SOURCE_SUFFIXES = {".py"}
OLLAMA_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
OLLAMA_PROBE_TTL_SECONDS = 30
POST_REQUEST_HEADER = "X-Requested-With"
POST_REQUEST_HEADER_VALUE = "CodeBrowser"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
_ollama_probe_lock = threading.RLock()
_ollama_probe_cache: tuple[float, tuple[str, ...], str, list[dict]] | None = None
LOGGER = logging.getLogger("code_browser")
LOCAL_REPOSITORY_EXCLUDES = """# Ollama Code Browser: local-only safety exclusions
.env
.env.*
!.env.example
!.env.sample
*.pem
*.key
*.p12
*.pfx
id_rsa*
id_ed25519*
credentials*.json
secrets.*
*.db
*.db-*
*.sqlite
*.sqlite3
data/
logs/
*.log
__pycache__/
*.py[cod]
.venv/
venv/
node_modules/
dist/
build/
.DS_Store
"""
PROJECT_METADATA_NAMES = {
    "readme", "readme.md", "readme.txt", "package.json", "pyproject.toml",
    "cargo.toml", "go.mod", "requirements.txt", "composer.json", "pom.xml",
    "build.gradle", "build.gradle.kts", "gemfile", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "wrangler.jsonc", "wrangler.toml",
}


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def loop_text(language: str, japanese: str, english: str) -> str:
    return english if language == "en" else japanese


def read_analysis_source(path: Path, language: str) -> bytes:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Analysis target is too large" if language == "en" else "解析対象のファイルが大きすぎます")
    return path.read_bytes()


def is_probably_binary(raw: bytes) -> bool:
    """Reject binary data without relying on often-inaccurate filename MIME types."""
    sample = raw[:8192]
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    control_bytes = sum(byte < 32 and byte not in {8, 9, 10, 12, 13} for byte in sample)
    return control_bytes / len(sample) > 0.10


def atomic_write_json(path: Path, value: object, prefix: str) -> None:
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=prefix, delete=False) as temporary:
            json.dump(value, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def resolve_static_file(relative: str, static_dir: Path = STATIC_DIR) -> Path | None:
    base = static_dir.resolve()
    path = (base / relative).resolve()
    return path if base in path.parents and path.is_file() else None


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without adding a dotenv dependency."""
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, value)


load_env_file(APP_DIR / ".env")


class OutsideRootError(PermissionError):
    """Raised when a requested path escapes the active browsing root."""


class CodeBrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], root: Path):
        super().__init__(address, RequestHandler)
        self.root_lock = threading.RLock()
        self.read_only_lock = threading.RLock()
        self.mcp_state_lock = threading.Lock()
        self._root = root.resolve()
        self._read_only = True
        self.loop_manager = LoopManager(self)

    def safe_path(self, relative: str) -> Path:
        candidate, _ = self.safe_path_with_root(relative)
        return candidate

    def safe_path_with_root(self, relative: str) -> tuple[Path, Path]:
        relative = unquote(relative).lstrip("/")
        with self.root_lock:
            root = self._root
            candidate = (root / relative).resolve()
            if candidate != root and root not in candidate.parents:
                raise OutsideRootError("Paths outside the browsing root cannot be accessed")
            return candidate, root

    @property
    def root(self) -> Path:
        with self.root_lock:
            return self._root

    def change_root(self, root: Path) -> None:
        with self.root_lock:
            self._root = root.resolve()

    @property
    def read_only(self) -> bool:
        with self.read_only_lock:
            return self._read_only

    @read_only.setter
    def read_only(self, value: bool) -> None:
        with self.read_only_lock:
            self._read_only = value


class RequestHandler(BaseHTTPRequestHandler):
    server: CodeBrowserServer

    def log_message(self, fmt: str, *args: object) -> None:
        LOGGER.info("client=%s request=%s", self.client_address[0], fmt % args)

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_json(self, status: int, value: object) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/config":
                root = self.server.root
                self.send_json(200, {
                    "root": str(root),
                    "rootName": root.name or str(root),
                    "parent": str(root.parent),
                    "maxFileBytes": MAX_FILE_BYTES,
                    "readOnly": self.server.read_only,
                })
            elif parsed.path == "/api/tree":
                self.handle_tree(parse_qs(parsed.query).get("path", [""])[0])
            elif parsed.path == "/api/file":
                self.handle_file(parse_qs(parsed.query).get("path", [""])[0])
            elif parsed.path == "/api/models":
                self.handle_models()
            elif parsed.path == "/api/loop/status":
                self.send_json(200, self.server.loop_manager.status())
            elif parsed.path == "/api/resolve-reference":
                query = parse_qs(parsed.query)
                self.handle_resolve_reference(
                    query.get("reference", [""])[0],
                    query.get("current", [""])[0],
                )
            elif parsed.path.startswith("/static/"):
                self.serve_static(parsed.path.removeprefix("/static/"))
            elif parsed.path == "/manifest.webmanifest":
                self.serve_static("manifest.webmanifest", content_type="application/manifest+json")
            elif parsed.path == "/service-worker.js":
                self.serve_static(
                    "service-worker.js",
                    content_type="text/javascript; charset=utf-8",
                    cache_control="no-cache, no-store, must-revalidate",
                    service_worker_allowed="/",
                )
            elif parsed.path == "/" or parsed.path == "/index.html":
                self.serve_static("index.html")
            else:
                self.send_error_json(404, "Not found")
        except (BrokenPipeError, ConnectionResetError) as exc:
            self.log_error("client disconnected during GET %s: %s", parsed.path, exc)
        except OutsideRootError as exc:
            self.send_error_json(403, str(exc))
        except PermissionError as exc:
            self.send_error_json(403, str(exc))
        except ValueError as exc:
            self.send_error_json(400, str(exc))
        except FileNotFoundError:
            self.send_error_json(404, "File or folder not found")
        except OSError as exc:
            self.send_error_json(500, f"Read failed: {exc}")

    def do_POST(self) -> None:
        endpoint = urlparse(self.path).path
        if endpoint not in {"/api/analyze", "/api/project-summary", "/api/root", "/api/file/save", "/api/git/commit", "/api/read-only", "/api/mcp-state", "/api/loop/start", "/api/loop/cancel"}:
            self.send_error_json(404, "Not found")
            return
        if self.headers.get(POST_REQUEST_HEADER) != POST_REQUEST_HEADER_VALUE:
            self.send_error_json(403, "This POST request did not originate from the Code Browser interface")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            max_length = 4_000_000 if endpoint == "/api/mcp-state" else 32_768 if endpoint in {"/api/root", "/api/git/commit", "/api/read-only", "/api/loop/start", "/api/loop/cancel"} else 500_000 if endpoint == "/api/project-summary" else MAX_FILE_BYTES * 2
            if length <= 0 or length > max_length:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if endpoint == "/api/root":
                self.handle_change_root(payload)
            elif endpoint == "/api/read-only":
                self.handle_read_only(payload)
            elif endpoint == "/api/mcp-state":
                self.handle_mcp_state(payload)
            elif endpoint == "/api/loop/start":
                self.handle_loop_start(payload)
            elif endpoint == "/api/loop/cancel":
                self.server.loop_manager.cancel()
                self.send_json(200, self.server.loop_manager.status())
            elif endpoint == "/api/file/save":
                self.handle_save_file(payload)
            elif endpoint == "/api/git/commit":
                self.handle_git_commit(payload)
            elif endpoint == "/api/project-summary":
                self.handle_project_summary(payload)
            else:
                self.handle_analyze(payload)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            self.send_error_json(400, str(exc))
        except OutsideRootError as exc:
            self.send_error_json(403, str(exc))
        except PermissionError as exc:
            self.send_error_json(403, str(exc))
        except FileNotFoundError:
            self.send_error_json(404, "File not found")
        except (BrokenPipeError, ConnectionResetError) as exc:
            self.log_error("client disconnected during POST %s: %s", endpoint, exc)
        except ConnectionError as exc:
            self.send_json(503, {"error": "Could not connect to Ollama", "detail": str(exc)})
        except OSError as exc:
            self.send_error_json(500, f"Operation failed: {exc}")

    def handle_change_root(self, payload: dict) -> None:
        raw_path = str(payload.get("path", "")).strip()
        if not raw_path:
            raise ValueError("A directory is required")
        new_root = Path(raw_path).expanduser()
        if not new_root.is_absolute():
            raise ValueError("The directory must be an absolute path")
        new_root = new_root.resolve()
        if not new_root.exists():
            raise FileNotFoundError
        if not new_root.is_dir():
            raise ValueError("The selected path is not a directory")
        if not os.access(new_root, os.R_OK | os.X_OK):
            raise PermissionError("The selected directory is not readable")
        self.server.change_root(new_root)
        self.send_json(200, {
            "root": str(new_root),
            "rootName": new_root.name or str(new_root),
            "parent": str(new_root.parent),
            "maxFileBytes": MAX_FILE_BYTES,
            "readOnly": self.server.read_only,
        })

    def handle_read_only(self, payload: dict) -> None:
        value = payload.get("readOnly")
        if not isinstance(value, bool):
            raise ValueError("readOnly must be a boolean")
        self.server.read_only = value
        self.send_json(200, {"readOnly": self.server.read_only})

    def handle_mcp_state(self, payload: dict) -> None:
        """Persist browser-owned metadata for the read-only MCP companion."""
        pinned = payload.get("pinnedProjects", [])
        analyses = payload.get("analyses", [])
        current = payload.get("current", {})
        if not isinstance(pinned, list) or not isinstance(analyses, list) or not isinstance(current, dict):
            raise ValueError("Invalid MCP synchronization data")

        clean_pinned: list[str] = []
        for value in pinned[:30]:
            path = str(value)[:4096]
            if Path(path).is_absolute() and path not in clean_pinned:
                clean_pinned.append(path)

        clean_analyses = []
        for item in analyses[-20:]:
            if not isinstance(item, dict):
                continue
            target = item.get("reportTarget") if isinstance(item.get("reportTarget"), dict) else {}
            clean_analyses.append({
                "id": str(item.get("id", ""))[:160],
                "title": str(item.get("title", ""))[:500],
                "mode": str(item.get("mode", ""))[:80],
                "model": str(item.get("model", ""))[:200],
                "host": str(item.get("host", ""))[:500],
                "status": str(item.get("status", ""))[:40],
                "language": str(item.get("language", ""))[:20],
                "projectRoot": str(item.get("projectRoot", ""))[:4096],
                "groupId": str(item.get("groupId", ""))[:160] if item.get("groupId") else None,
                "tabRole": str(item.get("tabRole", "standalone"))[:40],
                "target": {
                    "name": str(target.get("name", ""))[:500],
                    "path": str(target.get("path", ""))[:4096],
                },
                "content": str(item.get("content", ""))[:500_000],
            })

        state = {
            "version": 1,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "pinnedProjects": clean_pinned,
            "current": {
                "projectRoot": str(current.get("projectRoot", ""))[:4096],
                "filePath": str(current.get("filePath", ""))[:4096],
                "fileAbsolutePath": str(current.get("fileAbsolutePath", ""))[:4096],
                "readOnly": self.server.read_only,
            },
            "analyses": clean_analyses,
        }
        with self.server.mcp_state_lock:
            atomic_write_json(MCP_STATE_PATH, state, ".mcp-state.")
        self.send_json(200, {"synced": True, "analyses": len(clean_analyses), "pinnedProjects": len(clean_pinned)})

    def handle_loop_start(self, payload: dict) -> None:
        if self.server.read_only:
            self.send_error_json(423, "Disable READ ONLY before starting Loop")
            return
        result = self.server.loop_manager.start(payload)
        self.send_json(202, result)

    def handle_tree(self, relative: str) -> None:
        directory, root = self.server.safe_path_with_root(relative)
        if not directory.is_dir():
            raise FileNotFoundError
        items = []
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.casefold()),
            )
        except PermissionError:
            self.send_error_json(403, "This folder cannot be read")
            return
        for child in children[:1000]:
            if child.name in IGNORED_NAMES or child.name.startswith(".git"):
                continue
            try:
                resolved = child.resolve()
                if resolved != root and root not in resolved.parents:
                    continue
                is_dir = child.is_dir()
                size = child.stat().st_size if child.is_file() else None
            except OSError:
                continue
            items.append({
                "name": child.name,
                "path": child.relative_to(root).as_posix(),
                "type": "directory" if is_dir else "file",
                "size": size,
            })
        self.send_json(200, {"path": relative, "items": items, "truncated": len(children) > 1000})

    def handle_file(self, relative: str) -> None:
        path = self.server.safe_path(relative)
        if not path.is_file():
            raise FileNotFoundError
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            self.send_error_json(413, f"File is too large (limit: {MAX_FILE_BYTES // 1_000_000:.1f} MB)")
            return
        raw = path.read_bytes()
        if is_probably_binary(raw):
            self.send_error_json(415, "Binary files cannot be displayed")
            return
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")
        self.send_json(200, {
            "path": relative,
            "absolutePath": str(path),
            "name": path.name,
            "content": content,
            "size": size,
            "language": language_for(path.suffix),
            "lines": content.count("\n") + 1,
            "fingerprint": hashlib.sha256(raw).hexdigest(),
            "git": git_file_info(path),
        })

    def handle_save_file(self, payload: dict) -> None:
        if self.server.read_only:
            self.send_error_json(423, "Files cannot be saved while READ ONLY is enabled")
            return
        relative = str(payload.get("path", ""))
        content = str(payload.get("content", ""))
        expected = str(payload.get("fingerprint", ""))
        path = self.server.safe_path(relative)
        if not path.is_file():
            raise FileNotFoundError
        current = path.read_bytes()
        if expected and hashlib.sha256(current).hexdigest() != expected:
            self.send_error_json(409, "The file changed externally; reload it before editing")
            return
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            self.send_error_json(413, "The saved content exceeds the file-size limit")
            return
        mode = path.stat().st_mode
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.chmod(temporary_name, mode & 0o7777)
            os.replace(temporary_name, path)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)
        self.send_json(200, {
            "saved": True,
            "fingerprint": hashlib.sha256(encoded).hexdigest(),
            "size": len(encoded),
            "lines": content.count("\n") + 1,
            "git": git_file_info(path),
        })

    def handle_git_commit(self, payload: dict) -> None:
        if self.server.read_only:
            self.send_error_json(423, "Git commits are disabled while READ ONLY is enabled")
            return
        path = self.server.safe_path(str(payload.get("path", "")))
        message = str(payload.get("message", "")).strip()
        if not path.is_file():
            raise FileNotFoundError
        if not message or len(message) > 240:
            raise ValueError("Enter a commit message between 1 and 240 characters")
        info = git_file_info(path)
        if not info:
            raise ValueError("This file is not inside a Git repository")
        repository = Path(info["repoRoot"])
        relative = path.relative_to(repository).as_posix()
        run_git(repository, ["add", "--", relative])
        result = run_git(repository, ["commit", "--only", "-m", message, "--", relative])
        self.send_json(200, {"committed": True, "output": result.strip(), "git": git_file_info(path)})

    def handle_resolve_reference(self, reference: str, current: str) -> None:
        reference = reference.strip().strip("`'\"")
        if not reference or len(reference) > 300:
            raise ValueError("Invalid reference name")
        result = resolve_code_reference(self.server.root, reference, current)
        if not result:
            self.send_error_json(404, "Reference not found")
            return
        self.send_json(200, result)

    def probe_ollama(self) -> tuple[str, list[dict]]:
        return probe_ollama_models()

    def handle_models(self) -> None:
        try:
            host, models = self.probe_ollama()
        except ConnectionError as exc:
            self.send_json(503, {"error": "Could not connect to Ollama", "detail": str(exc)})
            return
        names = allowed_model_names(host, models)
        preferred = choose_model(names)
        self.send_json(200, {"host": host, "models": names, "preferred": preferred})

    def handle_project_summary(self, payload: dict) -> None:
        model = str(payload.get("model", ""))
        mode = str(payload.get("mode", "summary"))
        language = "en" if payload.get("language") == "en" else "ja"
        requested_root = Path(str(payload.get("root", self.server.root))).expanduser()
        if not requested_root.is_absolute():
            raise ValueError("Project root must be an absolute path" if language == "en" else "プロジェクトルートは絶対パスで指定してください")
        requested_root = requested_root.resolve()
        if not requested_root.is_dir() or not os.access(requested_root, os.R_OK | os.X_OK):
            raise ValueError("The selected project directory is unavailable" if language == "en" else "選択したプロジェクトディレクトリを利用できません")
        raw_target = str(payload.get("path", "")).strip()
        candidate = Path(raw_target).expanduser()
        target = candidate.resolve() if candidate.is_absolute() else (requested_root / raw_target.lstrip("/")).resolve()
        if target != requested_root and requested_root not in target.parents:
            raise PermissionError("The summary target is outside the selected project" if language == "en" else "構成要約の対象が選択したプロジェクトの外にあります")
        if not target.is_dir():
            raise ValueError("The project summary target must be a directory" if language == "en" else "構成要約の対象はディレクトリである必要があります")
        if mode == "consensus":
            reports = str(payload.get("reports", ""))[:120_000]
            snapshot = build_project_snapshot(target, max_depth=3, max_entries=600)
            if language == "en":
                prompt = (
                    f"Project: {target.name or str(target)}\nRoot: {target}\n\n"
                    "Act as the lead project reviewer. Combine the model reports into one decision-oriented result. "
                    "Use exactly these headings:\n## Shared findings\n## Disagreements and uncertainty\n"
                    "## Priority order\n## Recommended implementation plan\n"
                    "Deduplicate equivalent suggestions, distinguish consensus from single-model claims, and do not invent findings.\n\n"
                    f"{snapshot}\n\n# Model reports\n{reports}"
                )
                system = "You are a lead software architect consolidating independent project reviews in English Markdown. Wrap file paths and symbols in backticks."
            else:
                prompt = (
                    f"プロジェクト名: {target.name or str(target)}\nルート: {target}\n\n"
                    "主任レビュアーとしてモデル別レポートを統合してください。必ず次の見出しを使ってください。\n"
                    "## 共通している指摘\n## 意見の相違・不確実性\n## 優先順位\n## 推奨実装計画\n"
                    "同じ提案は重複排除し、複数モデルの合意と単独モデルの主張を区別し、レポートにない問題を創作しないでください。\n\n"
                    f"{snapshot}\n\n# モデル別レポート\n{reports}"
                )
                system = "あなたは複数のプロジェクトレビューを統合する主任ソフトウェアアーキテクトです。ファイルパスとシンボル名はバッククォートで囲んでください。"
        elif mode == "improve":
            snapshot = build_project_improvement_snapshot(target)
            if language == "en":
                prompt = (
                    f"Project: {target.name or str(target)}\nRoot: {target}\n\n"
                    "Review the project as a whole and identify concrete improvements. Prioritize by impact and provide evidence, expected benefit, and practical implementation steps. "
                    "Cover architecture, correctness, security, performance, maintainability, testing, and developer experience only when supported by the supplied files. "
                    "State sampling limitations and avoid generic advice.\n\n"
                    f"{snapshot}"
                )
                system = "You are an independent senior software architect reviewing an entire project in English Markdown. Wrap file paths and symbols in backticks."
            else:
                prompt = (
                    f"プロジェクト名: {target.name or str(target)}\nルート: {target}\n\n"
                    "プロジェクト全体をレビューし、具体的な改善点を影響度順に示してください。各項目に根拠、期待効果、実装手順を含め、"
                    "提供ファイルから判断できる場合だけ、設計、正確性、セキュリティ、性能、保守性、テスト、開発体験を扱ってください。"
                    "抜粋による制約を明記し、一般論は避けてください。\n\n"
                    f"{snapshot}"
                )
                system = "あなたはプロジェクト全体を独立評価する上級ソフトウェアアーキテクトです。ファイルパスとシンボル名はバッククォートで囲んでください。"
        elif language == "en":
            snapshot = build_project_snapshot(target)
            prompt = (
                f"Project: {target.name or str(target)}\nRoot: {target}\n\n"
                "Using only the directory structure and project metadata below, summarize the project in English.\n\n"
                "Use exactly these headings:\n## Project overview\n## Technology stack\n"
                "## Directory structure\n## Entry points and key files\n## Recommended reading order\n"
                "Do not present guesses as facts. State when the structure is insufficient to determine something.\n\n"
                f"{snapshot}"
            )
            system = "You are a software architect. Explain project structure accurately and concisely in English Markdown. Wrap file paths and symbol names in backticks."
        else:
            snapshot = build_project_snapshot(target)
            prompt = (
                f"プロジェクト名: {target.name or str(target)}\nルート: {target}\n\n"
                "以下はディレクトリ構成と主要メタデータです。記載された情報だけを根拠に、"
                "プロジェクト全体を日本語で要約してください。\n\n"
                "必ず次の見出しを使ってください。\n## プロジェクト概要\n## 技術スタック\n"
                "## ディレクトリ構成\n## 処理の入口と主要ファイル\n## 読み進める順序\n"
                "不明な項目は推測で断定せず「構成からは判断できない」と記載してください。\n\n"
                f"{snapshot}"
            )
            system = "あなたはソフトウェアアーキテクトです。プロジェクト構成を正確かつ簡潔なMarkdownで説明し、ファイルパスとシンボル名はバッククォートで囲んでください。"
        self.stream_project_summary(model, [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], language)

    def stream_ollama_chat(self, host: str, model: str, payload: dict, language: str) -> None:
        request = ollama_request(host, "/api/chat", payload=payload, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=300)
        except HTTPError as exc:
            if exc.code == 402:
                message = (
                    "Ollama Cloud requires payment or available credits for this model. Choose another model or check your Ollama plan."
                    if language == "en" else
                    "このモデルの実行にはOllama Cloudの支払いまたは利用可能なクレジットが必要です。別のモデルを選ぶか、Ollamaのプランを確認してください。"
                )
                self.send_error_json(402, message)
            else:
                message = f"Ollama request failed (HTTP {exc.code})" if language == "en" else f"Ollamaの実行に失敗しました（HTTP {exc.code}）"
                self.send_error_json(502, message)
            return
        except (URLError, TimeoutError, socket.timeout) as exc:
            message = f"Ollama request failed: {exc}" if language == "en" else f"Ollamaの実行に失敗しました: {exc}"
            self.send_error_json(502, message)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.write(json_bytes({"meta": {"host": host, "model": model}}) + b"\n")
        self.wfile.flush()
        with response:
            for line in response:
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    self.wfile.write(json_bytes({
                        "content": chunk.get("message", {}).get("content", ""),
                        "thinking": chunk.get("message", {}).get("thinking", ""),
                        "done": chunk.get("done", False),
                    }) + b"\n")
                    self.wfile.flush()
                except json.JSONDecodeError:
                    continue

    def stream_project_summary(self, model: str, messages: list[dict[str, str]], language: str) -> None:
        host, models = self.probe_ollama()
        available = allowed_model_names(host, models)
        if not model or model not in available:
            model = choose_model(available) or ""
        if not model:
            raise ValueError("No Ollama models are available" if language == "en" else "利用可能な Ollama モデルがありません")
        self.stream_ollama_chat(host, model, {
            "model": model,
            "stream": True,
            "messages": messages,
            "options": {"temperature": 0.2, "num_ctx": 32768},
        }, language)

    def handle_analyze(self, payload: dict) -> None:
        relative = str(payload.get("path", ""))
        mode = str(payload.get("mode", "explain"))
        model = str(payload.get("model", ""))
        selection = str(payload.get("selection", ""))
        language = "en" if payload.get("language") == "en" else "ja"
        path = self.server.safe_path(relative)
        if not path.is_file():
            raise FileNotFoundError
        raw = read_analysis_source(path, language)
        content = raw.decode("utf-8", errors="replace")
        target = selection.strip() or content
        if not target:
            raise ValueError("No code is available to analyze")
        if len(target) > 120_000:
            target = target[:120_000] + "\n\n[Remaining content omitted due to the size limit]"

        host, models = self.probe_ollama()
        available = allowed_model_names(host, models)
        if not model or model not in available:
            model = choose_model(available)
        if not model:
            raise ValueError("No Ollama models are available")

        instructions = ({
            "summary": "Summarize the code's purpose, main structure, inputs, outputs, and dependencies concisely.",
            "explain": "Explain the execution flow, important functions and classes, and data movement in clear English.",
            "review": "Review the code for possible bugs, security, performance, and maintainability. Give evidence and improvements.",
            "improve": "Focus exclusively on concrete improvements. Prioritize them by impact, explain the evidence and expected benefit, and include a practical implementation suggestion. Avoid generic advice and explicitly say when no change is warranted.",
            "consensus": "Act as the lead reviewer. Combine the model reports below into one decision-oriented result with these headings: Shared findings, Disagreements and uncertainty, Priority order, Recommended implementation plan. Deduplicate equivalent suggestions, distinguish model consensus from single-model claims, and do not invent findings absent from the reports.\n\nMODEL REPORTS:\n" + str(payload.get("question", ""))[:120000],
            "ask": str(payload.get("question", "Explain this code.")),
        } if language == "en" else {
            "summary": "コードの目的、主要な構成、入出力、依存関係を簡潔に要約してください。",
            "explain": "処理の流れを上から順に、重要な関数・クラス・データの動きを初心者にも分かる日本語で説明してください。",
            "review": "コードレビューを行い、バグ候補、セキュリティ、性能、保守性の順で、根拠と改善案を示してください。問題がなければ明記してください。",
            "improve": "具体的な改善点だけに特化してください。影響度順に、根拠、期待効果、実装方法を示してください。一般論は避け、変更不要な箇所はその旨を明記してください。",
            "consensus": "あなたは主任レビュアーです。以下のモデル別レポートを統合し、必ず「共通している指摘」「意見の相違・不確実性」「優先順位」「推奨実装計画」の見出しでまとめてください。同じ提案は重複排除し、複数モデルの合意と単独モデルの主張を区別し、レポートにない問題を創作しないでください。\n\nモデル別レポート:\n" + str(payload.get("question", ""))[:120000],
            "ask": str(payload.get("question", "このコードについて説明してください")),
        })
        prompt = (
            f"ファイル: {relative}\n"
            f"言語: {language_for(path.suffix)}\n"
            f"依頼: {instructions.get(mode, instructions['explain'])}\n\n"
            f"```\n{target}\n```"
        )
        system_message = (
            "You are an expert source-code analyst. Answer in English Markdown, clearly distinguish facts from assumptions, and wrap file paths and symbol names in backticks."
            if language == "en" else
            "あなたはソースコード読解の専門家です。回答は日本語で、推測と事実を分け、Markdownで読みやすく記述し、ファイルパスと関数・クラス名はバッククォートで囲んでください。"
        )
        ollama_payload = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.2, "num_ctx": 32768},
        }
        self.stream_ollama_chat(host, model, ollama_payload, language)

    def serve_static(
        self,
        relative: str,
        *,
        content_type: str | None = None,
        cache_control: str = "no-cache",
        service_worker_allowed: str | None = None,
    ) -> None:
        path = resolve_static_file(relative)
        if path is None:
            self.send_error_json(404, "Not found")
            return
        body = path.read_bytes()
        mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        if content_type is None and mime.startswith("text/"):
            mime = f"{mime}; charset=utf-8"
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if service_worker_allowed is not None:
            self.send_header("Service-Worker-Allowed", service_worker_allowed)
        self.end_headers()
        self.wfile.write(body)


def language_for(suffix: str) -> str:
    return {
        ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TSX", ".jsx": "JSX", ".html": "HTML",
        ".css": "CSS", ".scss": "SCSS", ".json": "JSON", ".md": "Markdown",
        ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
        ".c": "C", ".h": "C Header", ".cpp": "C++", ".hpp": "C++ Header",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".sh": "Shell",
        ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".sql": "SQL",
        ".vue": "Vue", ".svelte": "Svelte", ".cs": "C#",
    }.get(suffix.lower(), "Text")


def build_project_snapshot(root: Path, max_depth: int = 4, max_entries: int = 1200) -> str:
    """Build a bounded tree plus safe project metadata for LLM summarization."""
    entries: list[str] = []
    metadata_paths: list[Path] = []
    queue: deque[tuple[Path, int]] = deque([(root, 0)])
    while queue and len(entries) < max_entries:
        directory, depth = queue.popleft()
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except (OSError, PermissionError):
            continue
        for child in children:
            if len(entries) >= max_entries:
                break
            if child.name in IGNORED_NAMES or child.name.startswith(".git"):
                continue
            try:
                resolved = child.resolve()
                if resolved != root and root not in resolved.parents:
                    continue
                relative = child.relative_to(root).as_posix()
                if child.is_dir():
                    entries.append(f"D {relative}/")
                    if depth < max_depth:
                        queue.append((child, depth + 1))
                elif child.is_file():
                    size = child.stat().st_size
                    entries.append(f"F {relative} ({size} bytes)")
                    if depth <= 1 and child.name.casefold() in PROJECT_METADATA_NAMES and size <= 100_000:
                        metadata_paths.append(child)
            except OSError:
                continue

    parts = ["# ディレクトリ構成", "```text", *entries]
    if len(entries) >= max_entries:
        parts.append("[項目数上限のため以降省略]")
    parts.append("```")
    metadata_budget = 60_000
    for path in metadata_paths:
        if metadata_budget <= 0:
            break
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[:metadata_budget]
        except OSError:
            continue
        metadata_budget -= len(content)
        relative = path.relative_to(root).as_posix()
        parts.extend([f"\n# 主要ファイル: {relative}", "```", content, "```"])
    return "\n".join(parts)


def build_project_improvement_snapshot(root: Path) -> str:
    """Build a bounded project view with representative source files for review."""
    parts = [build_project_snapshot(root)]
    entry_names = {
        "main.py", "app.py", "server.py", "manage.py", "index.js", "index.ts",
        "main.js", "main.ts", "app.js", "app.ts", "main.go", "main.rs",
    }
    candidates = list(iter_source_files(root))
    candidates.sort(key=lambda path: (
        path.name.casefold() not in entry_names,
        len(path.relative_to(root).parts),
        path.relative_to(root).as_posix().casefold(),
    ))
    budget = 100_000
    included = 0
    parts.append("\n# Review source sample")
    for path in candidates:
        if budget <= 0 or included >= 30:
            break
        try:
            size = path.stat().st_size
            if size <= 0 or size > MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = content[:min(20_000, budget)]
        budget -= len(excerpt)
        included += 1
        relative = path.relative_to(root).as_posix()
        suffix_note = "\n[truncated]" if len(excerpt) < len(content) else ""
        parts.extend([f"\n## Source: {relative}", "```", excerpt + suffix_note, "```"])
    parts.append(f"\nSampled source files: {included}. The review must state that unsampled files were not inspected.")
    return "\n".join(parts)


SOURCE_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
    ".swift", ".vue", ".svelte", ".sh",
}


def resolve_code_reference(root: Path, reference: str, current: str = "") -> dict | None:
    """Resolve a file or symbol reference to a project-relative path and line."""
    clean = reference.strip()
    line_hint = 1
    line_match = re.search(r"(?::|#L)(\d+)$", clean)
    if line_match:
        line_hint = int(line_match.group(1))
        clean = clean[:line_match.start()]
    clean = clean.split("#", 1)[0].strip()
    file_like = "/" in clean or Path(clean).suffix.lower() in SOURCE_SUFFIXES or "." in Path(clean).name
    if file_like:
        direct_candidates = [(root / clean.lstrip("/")).resolve()]
        if current:
            current_path = (root / current.lstrip("/")).resolve()
            if current_path.is_file() and root in current_path.parents:
                if current_path.name == Path(clean).name:
                    direct_candidates.insert(0, current_path)
                parent = current_path.parent
                while parent == root or root in parent.parents:
                    direct_candidates.append((parent / clean).resolve())
                    if parent == root:
                        break
                    parent = parent.parent
        for direct in direct_candidates:
            if direct.is_file() and root in direct.parents:
                return {"path": direct.relative_to(root).as_posix(), "line": line_hint, "kind": "file", "reference": reference}
        basename = Path(clean).name
        for path in iter_source_files(root, include_all_text=True):
            if path.name == basename or path.relative_to(root).as_posix().endswith(clean):
                return {"path": path.relative_to(root).as_posix(), "line": line_hint, "kind": "file", "reference": reference}

    symbol = clean.removesuffix("()").split(".")[-1]
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", symbol):
        return None
    candidates: list[Path] = []
    if current:
        current_path = (root / current.lstrip("/")).resolve()
        if current_path.is_file() and root in current_path.parents:
            candidates.append(current_path)
    candidates.extend(path for path in iter_source_files(root) if path not in candidates)
    escaped = re.escape(symbol)
    symbol_pattern = re.compile(
        rf"^\s*(?:"
        rf"(?:async\s+)?def\s+{escaped}\b|"
        rf"(?:export\s+)?(?:async\s+)?function\s+{escaped}\b|"
        rf"(?:export\s+)?(?:const|let|var)\s+{escaped}\s*=|"
        rf"(?:pub\s+)?fn\s+{escaped}\b|"
        rf"func\s+(?:\([^)]*\)\s*)?{escaped}\b|"
        rf"(?:export\s+)?class\s+{escaped}\b|"
        rf"(?:async\s+)?{escaped}\s*\([^)]*\)\s*(?:\{{|:|=>)"
        rf")"
    )
    for path in candidates[:2500]:
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            source = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with source:
            for index, line in enumerate(source, 1):
                if index > 500:
                    break
                if symbol_pattern.search(line):
                    return {
                        "path": path.relative_to(root).as_posix(),
                        "line": index,
                        "kind": "symbol",
                        "reference": reference,
                        "preview": line.strip()[:240],
                    }
    return None


def iter_source_files(root: Path, include_all_text: bool = False):
    root = root.resolve()
    count = 0
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_NAMES and not name.startswith(".git")]
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if not include_all_text and path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            try:
                resolved = path.resolve()
                if root not in resolved.parents:
                    continue
            except OSError:
                continue
            yield path
            count += 1
            if count >= 5000:
                return


def configured_ollama_hosts() -> list[str]:
    """Use Ollama Cloud directly whenever an API key is configured."""
    if os.environ.get("OLLAMA_API_KEY"):
        return [OLLAMA_CLOUD_HOST]
    configured = os.environ.get("OLLAMA_HOSTS", "").strip()
    return [value.strip().rstrip("/") for value in configured.split(",") if value.strip()] or OLLAMA_HOSTS


def allowed_model_names(host: str, models: list[dict]) -> list[str]:
    """Return models allowed by the no-extra-cost policy for this app."""
    result: list[str] = []
    for model in models:
        name = model.get("name") or model.get("model")
        if not name:
            continue
        if host == OLLAMA_CLOUD_HOST and name in PAID_CLOUD_MODELS:
            continue
        result.append(name)
    return result


def validate_ollama_target(host: str, model: str | None = None) -> None:
    if host.rstrip("/") not in {value.rstrip("/") for value in configured_ollama_hosts()}:
        raise ConnectionError(f"Ollama host is not configured: {host}")
    if model is not None and not OLLAMA_MODEL_PATTERN.fullmatch(model):
        raise ValueError(f"Invalid Ollama model name: {model}")


def ollama_request(host: str, endpoint: str, *, payload: dict | None = None, headers: dict[str, str] | None = None) -> Request:
    model = str(payload.get("model", "")) if payload else None
    validate_ollama_target(host, model)
    request_headers = ollama_headers(host, headers)
    return Request(
        f"{host.rstrip('/')}/{endpoint.lstrip('/')}",
        data=json_bytes(payload) if payload is not None else None,
        headers=request_headers,
        method="POST" if payload is not None else "GET",
    )


def probe_ollama_models(*, use_cache: bool = True) -> tuple[str, list[dict]]:
    global _ollama_probe_cache
    now = time.monotonic()
    configured_hosts = tuple(configured_ollama_hosts())
    with _ollama_probe_lock:
        if (
            use_cache
            and _ollama_probe_cache
            and _ollama_probe_cache[1] == configured_hosts
            and now - _ollama_probe_cache[0] < OLLAMA_PROBE_TTL_SECONDS
        ):
            return _ollama_probe_cache[2], list(_ollama_probe_cache[3])
    errors = []
    for host in configured_hosts:
        try:
            timeout = 15 if host == OLLAMA_CLOUD_HOST else 3
            with urlopen(ollama_request(host, "/api/tags", headers={"Accept": "application/json"}), timeout=timeout) as response:
                models = json.load(response).get("models", [])
            if host.endswith("localhost:11434"):
                models = [item for item in models if item.get("name", "").endswith(LOCAL_CLOUD_SUFFIX)]
            with _ollama_probe_lock:
                _ollama_probe_cache = (time.monotonic(), configured_hosts, host, list(models))
            return host, models
        except (URLError, HTTPError, TimeoutError, socket.timeout, json.JSONDecodeError, ConnectionError, ValueError) as exc:
            errors.append(f"{host}: {exc}")
    raise ConnectionError(" / ".join(errors))


def run_git(repository: Path, arguments: list[str]) -> str:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout or "Git command failed").strip())
    return result.stdout


def git_file_info(path: Path) -> dict | None:
    try:
        root_result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if root_result.returncode != 0:
            return None
        repository = Path(root_result.stdout.strip()).resolve()
        relative = path.resolve().relative_to(repository).as_posix()
        status = run_git(repository, ["status", "--short", "--untracked-files=all", "--", relative]).strip()
        branch = run_git(repository, ["branch", "--show-current"]).strip()
        return {
            "repoRoot": str(repository),
            "relativePath": relative,
            "branch": branch,
            "status": status,
            "dirty": bool(status),
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def find_git_root(path: Path) -> Path | None:
    directory = path if path.is_dir() else path.parent
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def initialize_local_repository(root: Path, language: str = "ja") -> Path:
    """Create a local-only Git baseline for guarded Loop changes."""
    repository = root.resolve()
    if not repository.is_dir():
        raise ValueError(loop_text(language, "Gitリポジトリを作成するプロジェクトが見つかりません", "Could not find the project for local Git initialization"))
    run_git(repository, ["init"])
    exclude_path = repository / ".git" / "info" / "exclude"
    existing = exclude_path.read_text(encoding="utf-8", errors="replace") if exclude_path.is_file() else ""
    marker = "# Ollama Code Browser: local-only safety exclusions"
    if marker not in existing:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        exclude_path.write_text(existing + separator + LOCAL_REPOSITORY_EXCLUDES, encoding="utf-8")

    for key, fallback in (
        ("user.name", "Ollama Code Browser"),
        ("user.email", "ollama-code-browser@localhost"),
    ):
        configured = subprocess.run(
            ["git", "-C", str(repository), "config", "--get", key],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if configured.returncode != 0 or not configured.stdout.strip():
            run_git(repository, ["config", "--local", key, fallback])

    run_git(repository, ["add", "-A"])
    run_git(repository, ["commit", "--allow-empty", "-m", "Initial local snapshot for Ollama Loop"])
    return repository


def atomic_write_text(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    temporary_name = ""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        mode = 0o644
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, mode & 0o7777)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def discover_ollama_models() -> tuple[str, list[str]]:
    host, models = probe_ollama_models()
    return host, allowed_model_names(host, models)


def call_ollama_text(host: str, model: str, messages: list[dict[str, str]], *, json_format: bool = False) -> str:
    payload: dict[str, object] = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": 0.1, "num_ctx": 32768},
    }
    if json_format:
        payload["format"] = "json"
    request = ollama_request(host, "/api/chat", payload=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=300) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"{model}: Ollama HTTP {exc.code}") from exc
    except (URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{model}: Ollama request failed: {exc}") from exc
    return str(result.get("message", {}).get("content", "")).strip()


def build_loop_snapshot(target: Path, repository: Path) -> tuple[str, dict[str, str]]:
    target = target.resolve()
    repository = repository.resolve()
    candidates = [target] if target.is_file() else list(iter_source_files(target))
    candidates = [path for path in candidates if path.is_file() and path.suffix.lower() in LOOP_SOURCE_SUFFIXES]
    candidates.sort(key=lambda path: (len(path.relative_to(repository).parts), path.as_posix().casefold()))
    hashes: dict[str, str] = {}
    sections = [build_project_snapshot(target if target.is_dir() else target.parent, max_depth=3, max_entries=500)]
    budget = 95_000
    for path in candidates:
        if budget <= 0 or len(hashes) >= 12:
            break
        try:
            raw = path.read_bytes()
            if not raw or len(raw) > 35_000 or b"\x00" in raw[:8192]:
                continue
            content = raw.decode("utf-8")
            relative = path.relative_to(repository).as_posix()
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if len(content) > budget:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        hashes[relative] = digest
        sections.extend([
            f"\n## Editable full file: {relative}",
            f"SHA256: {digest}",
            "```",
            content,
            "```",
        ])
        budget -= len(content)
    return "\n".join(sections), hashes


def parse_loop_changes(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The integration model did not return valid JSON")
        value = json.loads(clean[start:end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("changes", []), list):
        raise ValueError("The integration model returned an invalid change format")
    return value


def detected_test_command(repository: Path) -> list[str] | None:
    python = repository / ".venv" / "bin" / "python"
    python_command = str(python) if python.is_file() else "python3"
    if (repository / "pyproject.toml").is_file() or (repository / "pytest.ini").is_file():
        return [python_command, "-m", "pytest"]
    if (repository / "tests").is_dir():
        return [python_command, "-m", "unittest", "discover", "-s", "tests"]
    return None


class LoopManager:
    """One guarded, persistent analyze-fix-test loop per Code Browser server."""

    def __init__(self, server: CodeBrowserServer):
        self.server = server
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.job: dict = self._load_previous()

    def _load_previous(self) -> dict:
        try:
            value = json.loads(LOOP_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                if value.get("status") in {"queued", "running"}:
                    value["status"] = "interrupted"
                    language = str(value.get("language", "ja"))
                    value["message"] = loop_text(language, "Code Browserの再起動によりLoopが中断されました", "Loop was interrupted because Code Browser restarted")
                terminal_round_status = {
                    "failed": "failed",
                    "cancelled": "cancelled",
                    "interrupted": "interrupted",
                }.get(str(value.get("status")), "failed")
                for round_result in value.get("rounds", []):
                    if isinstance(round_result, dict) and round_result.get("status") == "analyzing":
                        round_result["status"] = terminal_round_status
                        round_result.setdefault("error", str(value.get("message", "")))
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"status": "idle", "rounds": []}

    def _save(self) -> None:
        atomic_write_json(LOOP_STATE_PATH, self.job, ".loop-state.")

    def _update(self, **values: object) -> None:
        with self.lock:
            self.job.update(values)
            self.job["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def _update_round(self, round_result: dict, **values: object) -> None:
        with self.lock:
            round_result.update(values)
            self.job["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def status(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.job, ensure_ascii=False))

    def start(self, payload: dict) -> dict:
        language = "en" if payload.get("language") == "en" else "ja"
        with self.lock:
            if self.job.get("status") in {"queued", "running"}:
                raise ValueError(loop_text(language, "Loopはすでに実行中です", "A Loop is already running"))
        rounds = max(1, min(int(payload.get("rounds", 3)), 3))
        target_type = "file" if payload.get("targetType") == "file" else "project"
        relative = str(payload.get("path", ""))
        target = self.server.safe_path(relative)
        if target_type == "file" and not target.is_file():
            raise ValueError(loop_text(language, "ファイルLoopの対象がファイルではありません", "The file Loop target is not a file"))
        if target_type == "file" and target.suffix.lower() not in LOOP_SOURCE_SUFFIXES:
            raise ValueError(loop_text(language, "Loopは現在Python（.py）ファイルだけに対応しています", "Loop currently supports Python (.py) files only"))
        if target_type == "project" and not target.is_dir():
            raise ValueError(loop_text(language, "プロジェクトLoopの対象がディレクトリではありません", "The project Loop target is not a directory"))
        if target_type == "project" and not any(path.suffix.lower() in LOOP_SOURCE_SUFFIXES for path in iter_source_files(target)):
            raise ValueError(loop_text(language, "Python（.py）ファイルがないためLoopを開始できません", "Loop cannot start because the project contains no Python (.py) files"))
        repository = find_git_root(target)
        repository_initialized = False
        if not repository:
            repository = initialize_local_repository(self.server.root, language)
            repository_initialized = True
        if target != repository and repository not in target.parents:
            raise ValueError(loop_text(language, "Loopの対象がGitリポジトリ外です", "The Loop target is outside the Git repository"))
        if run_git(repository, ["status", "--porcelain"]).strip():
            raise ValueError(loop_text(language, "既存の変更を保護するため、GitワークツリーをcleanにしてからLoopを開始してください", "Clean the Git worktree before starting Loop so existing changes are protected"))
        models = [str(value) for value in payload.get("models", []) if str(value) and str(value) not in PAID_CLOUD_MODELS][:3]
        self.cancel_event = threading.Event()
        job_id = f"loop-{int(time.time())}"
        self.job = {
            "id": job_id,
            "status": "queued",
            "message": loop_text(language, "Loopを開始しています", "Starting Loop"),
            "language": language,
            "targetType": target_type,
            "targetPath": str(target),
            "repository": str(repository),
            "repositoryInitialized": repository_initialized,
            "requestedRounds": rounds,
            "models": models,
            "rounds": [],
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        threading.Thread(target=self._run, args=(target, repository, rounds, models, language), daemon=True).start()
        return self.status()

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.job.get("status") in {"queued", "running"}:
            with self.lock:
                for round_result in reversed(self.job.get("rounds", [])):
                    if round_result.get("status") == "analyzing":
                        round_result["status"] = "cancelled"
                        break
            language = str(self.job.get("language", "ja"))
            self._update(message=loop_text(language, "停止要求を受け付けました", "Stop requested"))

    def _run(self, target: Path, repository: Path, maximum_rounds: int, requested_models: list[str], language: str) -> None:
        try:
            host, available = discover_ollama_models()
            models = [model for model in requested_models if model in available]
            if len(models) < 3:
                preferred = [model for model in available if model not in PAID_CLOUD_MODELS]
                models = list(dict.fromkeys([*models, *preferred]))[:3]
            if not models:
                raise RuntimeError(loop_text(language, "利用可能なOllamaモデルがありません", "No Ollama models are available"))
            branch = f"ollama-loop/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            run_git(repository, ["checkout", "-b", branch])
            self._update(status="running", message=loop_text(language, "Round 1を解析中", "Analyzing Round 1"), branch=branch, models=models, host=host)
            for round_number in range(1, maximum_rounds + 1):
                if self.cancel_event.is_set():
                    self._update(status="cancelled", message=loop_text(language, "Loopを停止しました", "Loop stopped"))
                    return
                snapshot, editable_hashes = build_loop_snapshot(target, repository)
                if not editable_hashes:
                    raise RuntimeError(loop_text(language, "安全に編集できる小さなUTF-8ソースファイルが見つかりません", "No small, safely editable UTF-8 source files were found"))
                round_result: dict[str, object] = {
                    "number": round_number,
                    "status": "analyzing",
                    "analyses": [],
                    "changes": [],
                    "tests": None,
                }
                with self.lock:
                    self.job["rounds"].append(round_result)
                    self.job["message"] = loop_text(language, f"Round {round_number}: {len(models)}モデルで解析中", f"Round {round_number}: analyzing with {len(models)} models")
                    self._save()
                review_prompt = (
                    f"This is automated Python-only improvement round {round_number} of {maximum_rounds}. "
                    "Review only the supplied complete editable files. Identify high-confidence correctness, security, maintainability, or testability improvements that can be implemented now. "
                    f"Be concise, cite exact paths, do not suggest changes to truncated or absent files, and respond in {'English' if language == 'en' else 'Japanese'}.\n\n" + snapshot
                )
                analyses: list[dict[str, str]] = []
                with ThreadPoolExecutor(max_workers=len(models)) as executor:
                    futures = {
                        executor.submit(call_ollama_text, host, model, [
                            {"role": "system", "content": "You are a conservative senior code reviewer. Do not invent code or findings."},
                            {"role": "user", "content": review_prompt},
                        ]): model for model in models
                    }
                    for future in as_completed(futures):
                        model = futures[future]
                        try:
                            analyses.append({"model": model, "status": "complete", "content": future.result()[:20_000]})
                        except Exception as exc:
                            analyses.append({"model": model, "status": "failed", "content": str(exc)})
                self._update_round(round_result, analyses=analyses)
                successful = [item for item in analyses if item["status"] == "complete" and item["content"]]
                if not successful:
                    raise RuntimeError(loop_text(language, "すべてのモデル解析が失敗しました", "All model analyses failed"))
                if self.cancel_event.is_set():
                    self._update(status="cancelled", message=loop_text(language, "Loopを停止しました", "Loop stopped"))
                    return
                self._update(message=loop_text(language, f"Round {round_number}: 改善案を統合中", f"Round {round_number}: consolidating improvements"))
                reports = "\n\n---\n\n".join(f"## {item['model']}\n{item['content']}" for item in successful)
                response_language = "English" if language == "en" else "Japanese"
                integration_prompt = (
                    "Act as the implementation lead. Based only on the complete files and reviewer reports below, return one JSON object. "
                    "Schema: {\"summary\":string,\"changes\":[{\"path\":string,\"originalSha256\":string,\"newContent\":string,\"reason\":string}]}. "
                    "Paths must be repository-relative and must appear under 'Editable full file'. Preserve behavior unless fixing a supported issue. "
                    f"Return at most 8 files. If no safe change is warranted, return an empty changes array. Do not use markdown fences. Write summary and reason fields in {response_language}.\n\n"
                    + snapshot + "\n\n# Reviewer reports\n" + reports[:45_000]
                )
                integrated = None
                prepared_changes: list[dict] = []
                integration_attempts: list[dict[str, str]] = []
                for integration_model in models:
                    try:
                        integrated_text = call_ollama_text(host, integration_model, [
                            {"role": "system", "content": "You produce conservative, machine-applicable source edits as strict JSON."},
                            {"role": "user", "content": integration_prompt},
                        ], json_format=True)
                        candidate = parse_loop_changes(integrated_text)
                        candidate_changes = candidate.get("changes", [])[:8]
                        prepared_changes = prepare_loop_changes(candidate_changes, repository, editable_hashes, language)
                        integrated = candidate
                        integration_attempts.append({"model": integration_model, "status": "complete", "error": ""})
                        break
                    except Exception as exc:
                        integration_attempts.append({"model": integration_model, "status": "failed", "error": str(exc)[:4000]})
                self._update_round(round_result, integrationAttempts=integration_attempts)
                if integrated is None:
                    details = "; ".join(f"{item['model']}: {item['error']}" for item in integration_attempts)
                    raise RuntimeError(loop_text(language, f"すべての統合モデルが不正な変更を返しました: {details}", f"All integration models returned invalid changes: {details}"))
                self._update_round(round_result, summary=str(integrated.get("summary", ""))[:10_000])
                changes = prepared_changes
                if not changes:
                    self._update_round(round_result, status="no_changes")
                    self._update(status="completed", message=loop_text(language, f"Round {round_number}: 安全に適用できる変更はありませんでした", f"Round {round_number}: no further safe changes were found"))
                    return
                if self.server.read_only:
                    self._update(status="cancelled", message=loop_text(language, "READ ONLYが有効になったため、変更適用前に停止しました", "Stopped before applying changes because READ ONLY was enabled"))
                    return
                applied_paths: list[str] = []
                applied_records: list[dict[str, str]] = []
                originals: dict[Path, bytes] = {}
                try:
                    for change in changes:
                        if not isinstance(change, dict):
                            raise ValueError(loop_text(language, "変更項目の形式が不正です", "Invalid change item format"))
                        relative = str(change.get("path", ""))
                        requested_relative = str(change.get("requestedPath", relative))
                        path = (repository / relative).resolve()
                        if repository not in path.parents or not path.is_file():
                            raise ValueError(loop_text(language, f"リポジトリ外または存在しないファイルです: {relative}", f"File is outside the repository or does not exist: {relative}"))
                        raw = path.read_bytes()
                        actual_hash = hashlib.sha256(raw).hexdigest()
                        expected_hash = str(change.get("originalSha256", ""))
                        if actual_hash != editable_hashes[relative] or expected_hash != actual_hash:
                            raise ValueError(loop_text(language, f"解析後に変更されたファイルです: {relative}", f"File changed after analysis: {relative}"))
                        new_content = change.get("newContent")
                        if not isinstance(new_content, str) or len(new_content.encode("utf-8")) > MAX_FILE_BYTES:
                            raise ValueError(loop_text(language, f"保存内容が不正または大きすぎます: {relative}", f"Generated content is invalid or too large: {relative}"))
                        validate_generated_source(relative, new_content, language)
                        if new_content.encode("utf-8") == raw:
                            continue
                        originals[path] = raw
                        atomic_write_text(path, new_content)
                        applied_paths.append(relative)
                        additions = 0
                        deletions = 0
                        matcher = difflib.SequenceMatcher(a=raw.decode("utf-8").splitlines(), b=new_content.splitlines())
                        for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
                            if tag in {"replace", "delete"}:
                                deletions += before_end - before_start
                            if tag in {"replace", "insert"}:
                                additions += after_end - after_start
                        record = {
                            "path": relative,
                            "reason": str(change.get("reason", ""))[:2000],
                            "additions": additions,
                            "deletions": deletions,
                            "beforeSha256": actual_hash,
                            "afterSha256": hashlib.sha256(new_content.encode("utf-8")).hexdigest(),
                        }
                        if requested_relative != relative:
                            record["requestedPath"] = requested_relative
                        applied_records.append(record)
                except Exception:
                    restore_loop_files(originals)
                    raise
                if not applied_paths:
                    self._update_round(round_result, status="no_changes")
                    self._update(status="completed", message=loop_text(language, f"Round {round_number}: 実質的な変更はありませんでした", f"Round {round_number}: no effective changes were produced"))
                    return
                self._update_round(round_result, changes=applied_records)
                self._update(message=loop_text(language, f"Round {round_number}: テスト実行中", f"Round {round_number}: running tests"))
                command = detected_test_command(repository)
                if command:
                    try:
                        test = subprocess.run(command, cwd=repository, capture_output=True, text=True, timeout=180, check=False)
                        test_result = {
                            "command": command,
                            "exitCode": test.returncode,
                            "output": ((test.stdout or "") + (test.stderr or ""))[-30_000:],
                            "status": "passed" if test.returncode == 0 else "failed",
                        }
                        if test.returncode != 0:
                            self._update_round(round_result, tests=test_result)
                            restore_loop_files(originals)
                            raise RuntimeError(loop_text(language, f"テストが失敗したため変更を元に戻しました（exit {test.returncode}）", f"Tests failed, so the changes were rolled back (exit {test.returncode})"))
                    except subprocess.TimeoutExpired as exc:
                        output = ((exc.stdout or "") + (exc.stderr or "")) if isinstance(exc.stdout, str) else ""
                        test_result = {"command": command, "exitCode": None, "output": output[-30_000:], "status": "timed_out"}
                        self._update_round(round_result, tests=test_result)
                        restore_loop_files(originals)
                        raise RuntimeError(loop_text(language, "テストがタイムアウトしたため変更を元に戻しました", "Tests timed out, so the changes were rolled back"))
                else:
                    test_result = {"command": [], "exitCode": None, "output": loop_text(language, "テスト設定を検出できませんでした", "No test configuration was detected"), "status": "skipped"}
                self._update_round(round_result, tests=test_result)
                run_git(repository, ["add", "--", *applied_paths])
                commit_output = run_git(repository, ["commit", "-m", f"Ollama loop round {round_number}: automated improvements", "--", *applied_paths])
                self._update_round(
                    round_result,
                    commit=commit_output.strip().splitlines()[0] if commit_output.strip() else "",
                    status="complete",
                )
                if round_number < maximum_rounds:
                    self._update(message=loop_text(language, f"Round {round_number + 1}を解析中", f"Analyzing Round {round_number + 1}"))
            self._update(status="completed", message=loop_text(language, f"{maximum_rounds}ラウンドのLoopが完了しました", f"Completed all {maximum_rounds} Loop rounds"))
        except Exception as exc:
            with self.lock:
                for round_result in reversed(self.job.get("rounds", [])):
                    if round_result.get("status") == "analyzing":
                        round_result.update(status="failed", error=str(exc))
                        break
            self._update(status="failed", message=str(exc))


def ollama_headers(host: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    result = dict(headers or {})
    if host == OLLAMA_CLOUD_HOST:
        api_key = os.environ.get("OLLAMA_API_KEY")
        if not api_key:
            raise ConnectionError("OLLAMA_API_KEY is required to use Ollama Cloud directly")
        result["Authorization"] = f"Bearer {api_key}"
    return result


def resolve_loop_change_path(requested: str, editable_hashes: dict[str, str], language: str = "ja") -> str:
    """Resolve a model path only when the fallback basename is unambiguous."""
    clean = requested.strip().replace("\\", "/").removeprefix("./")
    if clean in editable_hashes:
        return clean
    basename = Path(clean).name
    matches = [path for path in editable_hashes if Path(path).name == basename]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(loop_text(language, f"編集許可されていないファイルです: {requested}", f"File is not authorized for editing: {requested}"))


def prepare_loop_changes(changes: list, repository: Path, editable_hashes: dict[str, str], language: str = "ja") -> list[dict]:
    """Validate a complete model proposal without writing any files."""
    prepared: list[dict] = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError(loop_text(language, "変更項目の形式が不正です", "Invalid change item format"))
        requested = str(change.get("path", ""))
        relative = resolve_loop_change_path(requested, editable_hashes, language)
        path = (repository / relative).resolve()
        if repository not in path.parents or not path.is_file():
            raise ValueError(loop_text(language, f"リポジトリ外または存在しないファイルです: {relative}", f"File is outside the repository or does not exist: {relative}"))
        raw = path.read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        expected_hash = str(change.get("originalSha256", ""))
        if actual_hash != editable_hashes[relative] or expected_hash != actual_hash:
            raise ValueError(loop_text(language, f"解析後に変更されたファイルです: {relative}", f"File changed after analysis: {relative}"))
        new_content = change.get("newContent")
        if not isinstance(new_content, str) or len(new_content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(loop_text(language, f"保存内容が不正または大きすぎます: {relative}", f"Generated content is invalid or too large: {relative}"))
        validate_generated_source(relative, new_content, language)
        normalized = dict(change)
        normalized["path"] = relative
        if requested != relative:
            normalized["requestedPath"] = requested
        prepared.append(normalized)
    return prepared


def validate_generated_source(relative: str, content: str, language: str = "ja") -> None:
    """Reject patch-shaped output and invalid Python before touching Git."""
    lines = content.splitlines()
    nonempty = [line for line in lines if line.strip()]
    patch_prefixed = [line for line in nonempty if line.startswith(("+", "-"))]
    if (
        content.lstrip().startswith("```")
        or "*** Begin Patch" in content
        or "diff --git " in content
        or (len(patch_prefixed) >= 3 and len(patch_prefixed) * 2 >= len(nonempty))
    ):
        raise ValueError(loop_text(language, f"差分記号を含む不正な全文が返されました: {relative}", f"Rejected invalid full-file content containing patch markers: {relative}"))
    if Path(relative).suffix.lower() == ".py":
        try:
            ast.parse(content, filename=relative)
        except SyntaxError as exc:
            raise ValueError(loop_text(language, f"Python構文エラーのため変更を拒否しました: {relative}:{exc.lineno}: {exc.msg}", f"Rejected change due to a Python syntax error: {relative}:{exc.lineno}: {exc.msg}")) from exc


def restore_loop_files(originals: dict[Path, bytes]) -> None:
    for path, raw in originals.items():
        atomic_write_text(path, raw.decode("utf-8"))


def choose_model(names: list[str]) -> str | None:
    """Pick a deterministic, code-oriented default from a server's model list."""
    return (
        next((name for name in names if "coder" in name.casefold() and "7b" in name.casefold()), None)
        or next((name for name in names if "coder" in name.casefold()), None)
        or next((name for name in names if "gpt-oss" in name.casefold()), None)
        or next((name for name in names if "qwen3.5" in name.casefold()), None)
        or next((name for name in names if name.endswith(":cloud")), None)
        or (names[0] if names else None)
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Ollama Code Browser")
    parser.add_argument("root", nargs="?", default=os.getcwd(), help="project root to browse")
    parser.add_argument("--host", default="127.0.0.1", help="listening host")
    parser.add_argument("--port", type=int, default=8092, help="listening port")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"folder not found: {root}")
    server = CodeBrowserServer((args.host, args.port), root)
    LOGGER.info("listening=http://%s:%s root=%s", args.host, args.port, root)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
