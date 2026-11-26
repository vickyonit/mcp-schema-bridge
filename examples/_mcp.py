"""Shared helper for the examples: list tools from (and call tools on) a stdio MCP server."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@contextlib.asynccontextmanager
async def mcp_session(argv: list[str]) -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(command=argv[0], args=argv[1:])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def list_tools(session: ClientSession) -> list[dict[str, Any]]:
    res = await session.list_tools()
    return [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in res.tools]
