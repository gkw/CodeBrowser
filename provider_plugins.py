"""Out-of-process provider plugin protocol for user-supplied LLM backends."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Sequence
from urllib.parse import urlparse


PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{2,127}$")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
PROTOCOL_VERSION = 1
MAX_MANIFEST_BYTES = 64_000
MAX_PLUGIN_OUTPUT_BYTES = 4_000_000


class PluginError(RuntimeError):
    """A provider plugin failed validation or execution."""


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    directory: Path
    entrypoint: Path
    environment: tuple[str, ...]
    description: str
    publisher: str
    license_name: str
    homepage: str

    @classmethod
    def load(cls, manifest_path: Path) -> "PluginManifest":
        manifest_path = manifest_path.resolve()
        if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise PluginError(f"Invalid plugin manifest: {manifest_path}")
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginError(f"Could not parse plugin manifest: {manifest_path}") from exc
        if not isinstance(value, dict):
            raise PluginError(f"Plugin manifest must be an object: {manifest_path}")
        allowed = {
            "id", "name", "version", "type", "protocolVersion", "entrypoint", "environment",
            "description", "publisher", "license", "homepage",
        }
        unknown = set(value) - allowed
        if unknown:
            raise PluginError(f"Unknown plugin manifest fields: {', '.join(sorted(unknown))}")
        plugin_id = value.get("id")
        name = value.get("name")
        version = value.get("version")
        if not isinstance(plugin_id, str) or not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise PluginError("Plugin id must contain lowercase letters, digits, dots, or hyphens")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise PluginError(f"Invalid plugin name: {plugin_id}")
        if not isinstance(version, str) or not version or len(version) > 40:
            raise PluginError(f"Invalid plugin version: {plugin_id}")
        if value.get("type") != "provider" or value.get("protocolVersion") != PROTOCOL_VERSION:
            raise PluginError(f"Unsupported plugin type or protocol: {plugin_id}")
        directory = manifest_path.parent
        raw_entrypoint = value.get("entrypoint")
        if not isinstance(raw_entrypoint, str) or not raw_entrypoint.endswith(".py"):
            raise PluginError(f"Provider plugin entrypoint must be a Python file: {plugin_id}")
        entrypoint = (directory / raw_entrypoint).resolve()
        if directory != entrypoint.parent and directory not in entrypoint.parents:
            raise PluginError(f"Plugin entrypoint escapes its directory: {plugin_id}")
        if not entrypoint.is_file():
            raise PluginError(f"Plugin entrypoint does not exist: {plugin_id}")
        raw_environment = value.get("environment", [])
        if not isinstance(raw_environment, list) or len(raw_environment) > 32:
            raise PluginError(f"Invalid environment allowlist: {plugin_id}")
        environment: list[str] = []
        for item in raw_environment:
            if not isinstance(item, str) or not ENVIRONMENT_NAME_PATTERN.fullmatch(item):
                raise PluginError(f"Invalid environment variable name: {plugin_id}")
            if item not in environment:
                environment.append(item)
        description = optional_manifest_text(value, "description", 500)
        publisher = optional_manifest_text(value, "publisher", 100)
        license_name = optional_manifest_text(value, "license", 80)
        homepage = optional_manifest_text(value, "homepage", 500)
        if homepage:
            parsed_homepage = urlparse(homepage)
            if parsed_homepage.scheme != "https" or not parsed_homepage.hostname:
                raise PluginError(f"Plugin homepage must use HTTPS: {plugin_id}")
        return cls(
            plugin_id, name.strip(), version, directory, entrypoint, tuple(environment),
            description, publisher, license_name, homepage,
        )


class PluginRegistry:
    def __init__(self, manifests: Mapping[str, PluginManifest]):
        self._manifests = dict(manifests)

    @classmethod
    def discover(cls, directories: Sequence[Path]) -> "PluginRegistry":
        manifests: dict[str, PluginManifest] = {}
        for parent in directories:
            resolved = parent.expanduser().resolve()
            if not resolved.is_dir():
                continue
            for manifest_path in sorted(resolved.glob("*/code-browser-plugin.json")):
                manifest = PluginManifest.load(manifest_path)
                if manifest.plugin_id in manifests:
                    raise PluginError(f"Duplicate plugin id: {manifest.plugin_id}")
                manifests[manifest.plugin_id] = manifest
        return cls(manifests)

    def get(self, plugin_id: str) -> PluginManifest:
        try:
            return self._manifests[plugin_id]
        except KeyError as exc:
            raise PluginError(f"Provider plugin is not installed: {plugin_id}") from exc

    def metadata(self) -> list[dict[str, str]]:
        return [
            {
                "id": manifest.plugin_id,
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "publisher": manifest.publisher,
                "license": manifest.license_name,
                "homepage": manifest.homepage,
            }
            for manifest in sorted(self._manifests.values(), key=lambda item: item.plugin_id)
        ]


class ProviderPluginClient:
    def __init__(self, manifest: PluginManifest, *, timeout_seconds: int = 300):
        self.manifest = manifest
        self.timeout_seconds = timeout_seconds

    def list_models(self) -> list[str]:
        result = self._call("models.list", {})
        raw_models = result.get("models")
        if not isinstance(raw_models, list):
            raise PluginError(f"Plugin returned an invalid model list: {self.manifest.plugin_id}")
        models: list[str] = []
        for value in raw_models:
            if not isinstance(value, str) or not MODEL_NAME_PATTERN.fullmatch(value):
                raise PluginError(f"Plugin returned an invalid model name: {self.manifest.plugin_id}")
            if value not in models:
                models.append(value)
        return models

    def infer(
        self,
        *,
        request_id: str,
        operation: str,
        model: str,
        messages: Sequence[Mapping[str, str]],
        maximum_output_tokens: int = 4096,
    ) -> dict[str, object]:
        if not MODEL_NAME_PATTERN.fullmatch(model):
            raise PluginError("Invalid provider model name")
        if maximum_output_tokens < 1 or maximum_output_tokens > 32_768:
            raise PluginError("Invalid provider output limit")
        normalized_messages: list[dict[str, str]] = []
        total_bytes = 0
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise PluginError("Invalid provider message")
            total_bytes += len(content.encode("utf-8"))
            normalized_messages.append({"role": role, "content": content})
        if not normalized_messages or len(normalized_messages) > 32 or total_bytes > 500_000:
            raise PluginError("Provider message context exceeds the protocol limit")
        result = self._call("inference.run", {
            "requestId": request_id,
            "operation": operation,
            "model": model,
            "messages": normalized_messages,
            "maximumOutputTokens": maximum_output_tokens,
        })
        content = result.get("content")
        if not isinstance(content, str):
            raise PluginError(f"Plugin response is missing content: {self.manifest.plugin_id}")
        usage = parse_usage(result.get("usage"))
        return {"content": content, "usage": usage}

    def _call(self, method: str, params: Mapping[str, object]) -> dict[str, object]:
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": "1",
            "method": method,
            "params": dict(params),
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
        environment = {"PYTHONIOENCODING": "utf-8", "CODE_BROWSER_PLUGIN_PROTOCOL": str(PROTOCOL_VERSION)}
        for name in self.manifest.environment:
            if name in os.environ:
                environment[name] = os.environ[name]
        try:
            completed = subprocess.run(
                [sys.executable, str(self.manifest.entrypoint)],
                input=request.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.manifest.directory,
                env=environment,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PluginError(f"Provider plugin timed out: {self.manifest.plugin_id}") from exc
        if completed.returncode != 0:
            raise PluginError(f"Provider plugin failed with exit code {completed.returncode}: {self.manifest.plugin_id}")
        if len(completed.stdout) > MAX_PLUGIN_OUTPUT_BYTES:
            raise PluginError(f"Provider plugin output exceeded the limit: {self.manifest.plugin_id}")
        try:
            response = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginError(f"Provider plugin returned invalid JSON: {self.manifest.plugin_id}") from exc
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0" or response.get("id") != "1":
            raise PluginError(f"Provider plugin returned an invalid response envelope: {self.manifest.plugin_id}")
        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code", "plugin_error")
            message = error.get("message", "Provider plugin request failed")
            raise PluginError(f"{self.manifest.plugin_id} [{code}]: {message}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise PluginError(f"Provider plugin returned no result: {self.manifest.plugin_id}")
        return result


def parse_usage(value: object) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PluginError("Provider plugin returned invalid usage")
    prompt = value.get("promptTokens")
    output = value.get("outputTokens")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in (prompt, output)):
        raise PluginError("Provider plugin returned invalid token counts")
    return {"promptTokens": prompt, "outputTokens": output}


def optional_manifest_text(value: Mapping[str, object], key: str, maximum: int) -> str:
    item = value.get(key, "")
    if not isinstance(item, str) or len(item) > maximum:
        raise PluginError(f"Invalid plugin manifest field: {key}")
    return item.strip()


def configured_plugin_directories(app_dir: Path) -> list[Path]:
    directories = [app_dir / "plugins" / "providers"]
    raw = os.environ.get("CODE_BROWSER_PLUGIN_DIRS", "")
    directories.extend(Path(item.strip()).expanduser() for item in raw.split(os.pathsep) if item.strip())
    return directories
