# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge[sdks,cli]"]
# ///
"""MCP server -> Claude (strict tools) -> MCP server.

  ANTHROPIC_API_KEY=... uv run examples/anthropic_loop.py -- npx -y @modelcontextprotocol/server-everything
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import anthropic

from mcp_schema_bridge import NormalizeOptions, denormalize_args, normalize_tools, to_sdk_payload

from _mcp import list_tools, mcp_session

MODEL = "claude-sonnet-5-5"


async def main(server: list[str], prompt: str) -> None:
    async with mcp_session(server) as session:
        # anthropic-strict has per-request budgets; strict_fallback keeps over-budget tools (non-strict)
        result = normalize_tools(await list_tools(session), "anthropic-strict", NormalizeOptions(strict_fallback=True))
        by_name = {t.name: t for t in result.tools}
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            tools=to_sdk_payload(result, "anthropic-messages"),
        )
        for block in message.content:
            if block.type != "tool_use" or block.name not in by_name:
                continue
            args: Any = denormalize_args(by_name[block.name], block.input).args
            outcome = await session.call_tool(block.name, arguments=args)
            print(f"{block.name}({args}) -> {outcome}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else ["npx", "-y", "@modelcontextprotocol/server-everything"]
    asyncio.run(main(argv, "Use the echo tool to echo 'hello from Claude'."))
