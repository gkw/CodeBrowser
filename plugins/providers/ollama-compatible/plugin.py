#!/usr/bin/env python3
"""Reference BYOK provider for Ollama and Ollama-compatible APIs."""

from __future__ import annotations

import json
import os
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def respond(request_id: object, *, result: object = None, error: tuple[str, str] | None = None) -> None:
    value: dict[str, object] = {"jsonrpc": "2.0", "id": request_id}
    if error:
        value["error"] = {"code": error[0], "message": error[1]}
    else:
        value["result"] = result
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()


def configuration() -> tuple[str, str]:
    base_url = os.environ.get("OLLAMA_PLUGIN_BASE_URL", "http://localhost:11434").rstrip("/")
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
    ):
        raise ValueError("OLLAMA_PLUGIN_BASE_URL is invalid")
    return base_url, os.environ.get("OLLAMA_PLUGIN_API_KEY", "")


def api_request(path: str, *, payload: object | None = None) -> object:
    base_url, api_key = configuration()
    headers = {"Accept": "application/json", "User-Agent": "CodeBrowserProviderPlugin/1.0"}
    data = None
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=300 if data is not None else 10) as response:
            raw = response.read(4_000_001)
    except HTTPError as exc:
        raise RuntimeError(f"Provider returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError("Could not connect to the configured provider") from exc
    if len(raw) > 4_000_000:
        raise RuntimeError("Provider response exceeded the size limit")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Provider returned invalid JSON") from exc


def list_models() -> dict[str, object]:
    value = api_request("/api/tags")
    if not isinstance(value, dict):
        raise RuntimeError("Provider model response is invalid")
    models = []
    for item in value.get("models", []):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            models.append(item["name"])
    return {"models": models}


def infer(params: object) -> dict[str, object]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    model = params.get("model")
    messages = params.get("messages")
    maximum = params.get("maximumOutputTokens")
    if (
        not isinstance(model, str) or not isinstance(messages, list) or isinstance(maximum, bool)
        or not isinstance(maximum, int) or maximum < 1 or maximum > 32_768
    ):
        raise ValueError("inference params are invalid")
    value = api_request("/api/chat", payload={
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": 0.2, "num_predict": maximum, "num_ctx": 32768},
    })
    if not isinstance(value, dict) or not isinstance(value.get("message"), dict):
        raise RuntimeError("Provider inference response is invalid")
    message = value["message"]
    result: dict[str, object] = {"content": str(message.get("content", ""))}
    prompt = value.get("prompt_eval_count")
    output = value.get("eval_count")
    if all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in (prompt, output)):
        result["usage"] = {"promptTokens": prompt, "outputTokens": output}
    return result


def main() -> None:
    request_id: object = None
    try:
        raw = sys.stdin.buffer.readline(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Protocol request exceeds the size limit")
        request = json.loads(raw)
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            raise ValueError("Invalid JSON-RPC request")
        request_id = request.get("id")
        method = request.get("method")
        if method == "models.list":
            respond(request_id, result=list_models())
        elif method == "inference.run":
            respond(request_id, result=infer(request.get("params")))
        else:
            respond(request_id, error=("method_not_found", "Unsupported provider method"))
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        respond(request_id, error=("provider_error", str(exc)))


if __name__ == "__main__":
    main()
