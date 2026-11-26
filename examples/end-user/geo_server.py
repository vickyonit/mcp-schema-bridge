# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.3", "anyio"]
# ///
"""A third-party MCP server you don't control. Its schemas look like what older JSON Schema
generators emit: a draft-07 tuple for coordinates and a mixed-type enum."""

import json
import math

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

POINT = {"type": "array", "items": [{"type": "number"}, {"type": "number"}], "minItems": 2, "maxItems": 2}

TOOLS = [
    types.Tool(
        name="distance",
        description="Distance in km between two points given as [latitude, longitude].",
        input_schema={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "from": POINT,
                "to": POINT,
                "precision": {"type": ["string", "integer"], "enum": ["exact", 0, 1, 2], "description": "decimals or 'exact'"},
            },
            "required": ["from", "to"],
        },
    )
]


async def list_tools(ctx, params):  # type: ignore[no-untyped-def]
    return types.ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params):  # type: ignore[no-untyped-def]
    a, b = params.arguments["from"], params.arguments["to"]
    la1, lo1, la2, lo2 = map(math.radians, [*a, *b])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    km = round(2 * 6371 * math.asin(math.sqrt(h)), 1)
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps({"km": km, "received": params.arguments}))])


async def main() -> None:
    server = Server("geo", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
