# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge[cli]", "openai>=1.99"]
# ///
"""A minimal MCP client/agent: connect to an MCP server, let an OpenAI model call its tools.

  OPENAI_API_KEY=... uv run agent.py --raw -- <server command>   # what most clients do today
  OPENAI_API_KEY=... uv run agent.py -- <server command>         # with mcp-schema-bridge
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import BadRequestError, OpenAI

from mcp_schema_bridge import NormalizeOptions, denormalize_args, normalize_tools, to_sdk_payload

MODEL = "gpt-4.1-mini"


async def run(server: list[str], prompt: str, raw: bool) -> None:
    params = StdioServerParameters(command=server[0], args=server[1:])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as mcp:
        await mcp.initialize()
        mcp_tools = (await mcp.list_tools()).tools
        client = OpenAI()

        if raw:  # pass MCP schemas straight through, strict mode on
            tools = [{"type": "function", "name": t.name, "description": t.description or "",
                      "parameters": t.input_schema, "strict": True} for t in mcp_tools]
            bridged = None
        else:
            bridged = normalize_tools(mcp_tools, "openai-strict", NormalizeOptions(strict_fallback=True))
            print(bridged.summary(), file=sys.stderr)  # what changed, and how a server could avoid it
            tools = to_sdk_payload(bridged, "openai-responses")

        try:
            response = client.responses.create(model=MODEL, input=prompt, tools=tools, tool_choice="required")
        except BadRequestError as e:
            print(f"OpenAI rejected the tools: {e.message}")
            return

        for item in response.output:
            if item.type != "function_call":
                continue
            args = json.loads(item.arguments)
            print(f"model called {item.name}({json.dumps(args)})")
            tool = bridged.get(item.name) if bridged else None
            if tool is not None:
                args = denormalize_args(tool, args).args
                print(f"  -> sent to MCP server: {json.dumps(args)}")
            result = await mcp.call_tool(item.name, args)
            print(f"  <- {result.content[0].text if result.content else result}")  # type: ignore[union-attr]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="send MCP schemas unchanged")
    ap.add_argument("--prompt", default="Search for 'lamps', only 5 results, sorted by date.")
    ap.add_argument("server", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    server = a.server[1:] if a.server[:1] == ["--"] else a.server
    asyncio.run(run(server, a.prompt, a.raw))


if __name__ == "__main__":
    main()
