"""Exercise a deployed Streamable HTTP server with the real MCP client."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--expected-tool", action="append", default=[])
    return parser


async def _run(url: str, token: str, expected_tools: list[str]) -> None:
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
        async with Client(streamable_http_client(url, http_client=http_client)) as client:
            tools = await client.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            missing = sorted(set(expected_tools) - set(names))
            if missing:
                raise RuntimeError(f"missing expected tools: {missing}; registered: {names}")
            result = await client.call_tool("list_models", {})
            if result.is_error:
                raise RuntimeError(f"list_models failed: {result.content}")
            print(json.dumps({"registered_tools": names, "list_models": result.structured_content}, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    asyncio.run(_run(args.url, args.token, args.expected_tool))


if __name__ == "__main__":
    main()
