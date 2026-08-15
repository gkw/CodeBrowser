#!/usr/bin/env python3
"""Small protocol-level smoke test for the Code Browser MCP server."""

from __future__ import annotations

import argparse
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def check(url: str) -> None:
    try:
        async with streamable_http_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                context = await session.call_tool("get_current_context", {})
                pinned = await session.call_tool("list_pinned_projects", {})
                results = await session.call_tool("list_analysis_results", {"limit": 5})
                loop = await session.call_tool("get_loop_status", {})
                print(f"server={initialized.server_info.name} version={initialized.server_info.version}")
                print("tools=" + ",".join(tool.name for tool in tools.tools))
                print(f"context_error={context.is_error} pinned_error={pinned.is_error} results_error={results.is_error} loop_error={loop.is_error}")
    except Exception as exc:
        print(f"ERROR: Could not connect to MCP server at {url}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8766/mcp")
    arguments = parser.parse_args()
    asyncio.run(check(arguments.url))


if __name__ == "__main__":
    main()
