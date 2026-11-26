# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge[sdks,cli]"]
# ///
"""MCP server -> Gemini -> MCP server, with schemas normalized for gemini-json.

  GEMINI_API_KEY=... uv run examples/gemini_loop.py -- npx -y @modelcontextprotocol/server-everything
"""

from __future__ import annotations

import asyncio
import sys

from google import genai
from google.genai import types

from mcp_schema_bridge import denormalize_args, normalize_tools, to_sdk_payload

from _mcp import list_tools, mcp_session

MODEL = "gemini-3.5-flash-lite"


async def main(server: list[str], prompt: str) -> None:
    async with mcp_session(server) as session:
        result = normalize_tools(await list_tools(session), "gemini-json")
        for entry in result.report.entries:
            if entry.severity in ("lossy", "fatal"):
                print(f"[{entry.severity}] {entry.tool}: {entry.message}", file=sys.stderr)
        by_name = {t.name: t for t in result.tools}

        client = genai.Client()  # reads GEMINI_API_KEY
        config = types.GenerateContentConfig(tools=to_sdk_payload(result, "genai"))
        response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
        for call in response.function_calls or []:
            if call.name not in by_name:
                continue
            args = denormalize_args(by_name[call.name], call.args or {}).args
            outcome = await session.call_tool(call.name, arguments=args)
            print(f"{call.name}({args}) -> {outcome}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else ["npx", "-y", "@modelcontextprotocol/server-everything"]
    asyncio.run(main(argv, "Use the echo tool to echo 'hello from Gemini'."))
