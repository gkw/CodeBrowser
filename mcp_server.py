#!/usr/bin/env python3
"""Read-only MCP companion for Ollama Code Browser."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer


APP_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = APP_DIR / ".code-browser-mcp-state.json"
DEFAULT_LOOP_STATE_PATH = APP_DIR / ".code-browser-loop-state.json"

mcp = MCPServer(
    name="ollama-code-browser",
    title="Ollama Code Browser",
    description="Read pinned projects and generated code analysis results from Ollama Code Browser.",
    version="1.0.0",
    instructions=(
        "This server is read-only. Use list_pinned_projects to discover projects, "
        "list_analysis_results to find summaries or improvements, and "
        "get_analysis_result only when the user needs the full generated content."
    ),
)


def state_path() -> Path:
    configured = os.environ.get("CODE_BROWSER_MCP_STATE", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_STATE_PATH


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {
            "version": 1,
            "updatedAt": None,
            "pinnedProjects": [],
            "current": {},
            "analyses": [],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Code Browser state could not be read: {exc}") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise RuntimeError("Code Browser state has an unsupported format")
    return value


def load_loop_state() -> dict[str, Any]:
    configured = os.environ.get("CODE_BROWSER_LOOP_STATE", "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_LOOP_STATE_PATH
    if not path.is_file():
        return {"status": "idle", "rounds": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Code Browser Loop state could not be read: {exc}") from exc
    return value if isinstance(value, dict) else {"status": "idle", "rounds": []}


def project_name(path: str) -> str:
    return Path(path).name or path


READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": False,
}


@mcp.tool(
    title="List pinned Code Browser projects",
    description="List projects pinned by the user in Ollama Code Browser. Use this before choosing a project.",
    annotations=READ_ONLY,
    structured_output=True,
)
def list_pinned_projects() -> dict[str, Any]:
    state = load_state()
    current_root = str(state.get("current", {}).get("projectRoot", ""))
    projects = [
        {
            "name": project_name(path),
            "path": path,
            "isCurrent": path == current_root,
        }
        for path in state.get("pinnedProjects", [])
        if isinstance(path, str)
    ]
    return {"projects": projects, "count": len(projects), "updatedAt": state.get("updatedAt")}


@mcp.tool(
    title="Get current Code Browser context",
    description="Get the project and file currently open in Ollama Code Browser, its read-only state, and result counts.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_current_context() -> dict[str, Any]:
    state = load_state()
    current = dict(state.get("current", {}))
    current["analysisCount"] = len(state.get("analyses", []))
    current["pinnedProjectCount"] = len(state.get("pinnedProjects", []))
    current["updatedAt"] = state.get("updatedAt")
    return current


@mcp.tool(
    title="List Code Browser analysis results",
    description=(
        "List generated project summaries, file summaries, explanations, reviews, and improvement results. "
        "Optionally filter by exact project root and result mode. Returns metadata and previews, not full content."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def list_analysis_results(
    project_root: str | None = None,
    mode: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    state = load_state()
    limit = max(1, min(limit, 20))
    results = []
    for item in reversed(state.get("analyses", [])):
        if not isinstance(item, dict):
            continue
        if project_root and item.get("projectRoot") != project_root:
            continue
        if mode and item.get("mode") != mode:
            continue
        content = str(item.get("content", ""))
        results.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "mode": item.get("mode"),
            "model": item.get("model"),
            "status": item.get("status"),
            "projectRoot": item.get("projectRoot"),
            "target": item.get("target"),
            "groupId": item.get("groupId"),
            "tabRole": item.get("tabRole"),
            "contentLength": len(content),
            "preview": content[:600],
        })
        if len(results) >= limit:
            break
    return {"results": results, "count": len(results), "updatedAt": state.get("updatedAt")}


@mcp.tool(
    title="Get a Code Browser analysis result",
    description="Get the full generated content for one analysis ID returned by list_analysis_results.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_analysis_result(analysis_id: str) -> dict[str, Any]:
    if not analysis_id or len(analysis_id) > 160:
        raise ValueError("A valid analysis_id is required")
    state = load_state()
    for item in state.get("analyses", []):
        if isinstance(item, dict) and item.get("id") == analysis_id:
            return {
                "id": item.get("id"),
                "title": item.get("title"),
                "mode": item.get("mode"),
                "model": item.get("model"),
                "host": item.get("host"),
                "status": item.get("status"),
                "language": item.get("language"),
                "projectRoot": item.get("projectRoot"),
                "target": item.get("target"),
                "groupId": item.get("groupId"),
                "tabRole": item.get("tabRole"),
                "content": item.get("content", ""),
                "updatedAt": state.get("updatedAt"),
            }
    raise ValueError(f"Analysis result not found: {analysis_id}")


@mcp.tool(
    title="Get Code Browser Loop status",
    description="Get the current or most recent automated analyze-fix-test Loop job, including target, branch, progress, and round summaries.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_loop_status() -> dict[str, Any]:
    job = load_loop_state()
    rounds = []
    for item in job.get("rounds", []):
        if not isinstance(item, dict):
            continue
        rounds.append({
            "number": item.get("number"),
            "status": item.get("status"),
            "summary": item.get("summary", ""),
            "changes": item.get("changes", []),
            "tests": item.get("tests"),
            "commit": item.get("commit"),
            "models": [analysis.get("model") for analysis in item.get("analyses", []) if isinstance(analysis, dict)],
        })
    return {
        "id": job.get("id"),
        "status": job.get("status", "idle"),
        "message": job.get("message", ""),
        "targetType": job.get("targetType"),
        "targetPath": job.get("targetPath"),
        "repository": job.get("repository"),
        "branch": job.get("branch"),
        "models": job.get("models", []),
        "requestedRounds": job.get("requestedRounds"),
        "rounds": rounds,
        "startedAt": job.get("startedAt"),
        "updatedAt": job.get("updatedAt"),
    }


@mcp.tool(
    title="Get a Code Browser Loop round",
    description="Get model-by-model analysis, applied changes, test output, and commit for one round of the latest Loop job.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_loop_round(round_number: int) -> dict[str, Any]:
    if round_number < 1 or round_number > 3:
        raise ValueError("round_number must be between 1 and 3")
    job = load_loop_state()
    for item in job.get("rounds", []):
        if isinstance(item, dict) and item.get("number") == round_number:
            return {"jobId": job.get("id"), **item}
    raise ValueError(f"Loop round not found: {round_number}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ollama Code Browser read-only MCP server")
    parser.add_argument("--host", default=os.environ.get("CODE_BROWSER_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODE_BROWSER_MCP_PORT", "8766")))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    mcp.run(
        transport="streamable-http",
        host=arguments.host,
        port=arguments.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
