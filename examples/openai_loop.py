# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge[sdks,cli]"]
# ///
"""MCP server -> OpenAI (Responses API, strict tools) -> MCP server.

  OPENAI_API_KEY=... uv run examples/openai_loop.py -- npx -y @modelcontextprotocol/server-everything
"""

from __future__ import annotations

import asyncio
import json
import sys

from openai import OpenAI

from mcp_schema_bridge import NormalizeOptions, denormalize_args, normalize_tools, to_sdk_payload

from _mcp import list_tools, mcp_session

MODEL = "gpt-5-mini"


async def main(server: list[str], prompt: str) -> None:
    async with mcp_session(server) as session:
        # strict_fallback: tools that cannot be strict are still offered, non-strict
        result = normalize_tools(await list_tools(session), "openai-strict", NormalizeOptions(strict_fallback=True))
        by_name = {t.name: t for t in result.tools}
        client = OpenAI()  # reads OPENAI_API_KEY
        response = client.responses.create(model=MODEL, input=prompt, tools=to_sdk_payload(result, "openai-responses"))
        for item in response.output:
            if item.type != "function_call" or item.name not in by_name:
                continue
            # strict mode sends null for "not provided"; denormalize_args removes those again
            args = denormalize_args(by_name[item.name], json.loads(item.arguments)).args
            outcome = await session.call_tool(item.name, arguments=args)
            print(f"{item.name}({args}) -> {outcome}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else ["npx", "-y", "@modelcontextprotocol/server-everything"]
    asyncio.run(main(argv, "Use the echo tool to echo 'hello from OpenAI'."))
