"""Low-level MCP server that echoes the exact arguments it receives (proxy tests)."""

import json

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

TOOLS = [
    types.Tool(
        name="search",
        description="Search things",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer"},
                "kind": {"type": "string", "const": "web"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="say",
        description="Root is a plain string",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    ),
    types.Tool(
        name="tag",
        description="Open map: rejected by strict targets",
        input_schema={
            "type": "object",
            "properties": {
                "labels": {"type": "object", "additionalProperties": {"type": "string"}}
            },
            "required": ["labels"],
        },
    ),
]


async def list_tools(ctx, params):  # type: ignore[no-untyped-def]
    return types.ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params):  # type: ignore[no-untyped-def]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(params.arguments, sort_keys=True))]
    )


async def main() -> None:
    server = Server("raw", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
