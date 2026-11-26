"""`mcp-schema-bridge proxy`: an MCP server that fronts another MCP server.

It lists the upstream server's tools with input schemas normalized for one target model API, and
maps the model's arguments back (denormalize_args) before forwarding tools/call upstream. Use it
when you cannot change the MCP client or the MCP server (e.g. a desktop app talking to Gemini).

Tools only in this version: resources and prompts are not proxied.
Requires the ``cli`` extra (the official MCP SDK).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO, cast

from mcp_schema_bridge._version import __version__
from mcp_schema_bridge.core.options import NormalizeOptions
from mcp_schema_bridge.core.reverse import denormalize_args
from mcp_schema_bridge.core.rules import Target
from mcp_schema_bridge.core.toolset import normalize_tools


async def run_proxy(
    argv: list[str],
    target: Target,
    opts: NormalizeOptions,
    *,
    report_path: str | None = None,
    log: TextIO = sys.stderr,
) -> None:
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    # Upstream servers often need the user's environment (API tokens, PATH for npx/uvx).
    params = StdioServerParameters(command=argv[0], args=argv[1:], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as upstream:
        init: Any = await upstream.initialize()
        raw: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page: Any = await upstream.list_tools(
                params=types.PaginatedRequestParams(cursor=cursor) if cursor else None
            )
            raw += [
                cast(dict[str, Any], t.model_dump(mode="json", by_alias=True, exclude_none=True))
                for t in page.tools
            ]
            cursor = page.next_cursor
            if not cursor:
                break

        result = normalize_tools(
            [{k: t[k] for k in ("name", "description", "inputSchema") if k in t} for t in raw],
            target,
            opts,
        )
        by_name = {t.name: t for t in result.tools}
        originals = {t["name"]: t for t in raw}
        served = [
            types.Tool.model_validate({**originals[t.name], "inputSchema": t.schema})
            for t in result.tools
        ]
        _log_summary(log, init, target, result)
        if report_path:
            Path(report_path).write_text(
                json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        async def list_tools(ctx: Any, params: Any) -> Any:
            return types.ListToolsResult(tools=served)

        async def call_tool(ctx: Any, params: Any) -> Any:
            tool = by_name.get(params.name)
            if tool is None:
                return types.CallToolResult(
                    is_error=True,
                    content=[
                        types.TextContent(
                            type="text",
                            text=f"tool {params.name!r} is not available through mcp-schema-bridge for {target}",
                        )
                    ],
                )
            args = denormalize_args(tool, params.arguments or {}).args
            return await upstream.call_tool(params.name, args)

        info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
        upstream_name = getattr(info, "name", "upstream")
        server = Server(
            f"{upstream_name} (via mcp-schema-bridge)",
            version=__version__,
            instructions=getattr(init, "instructions", None),
            on_list_tools=list_tools,
            on_call_tool=call_tool,
        )
        async with stdio_server() as (sr, sw):
            await server.run(sr, sw, server.create_initialization_options())


def _log_summary(log: TextIO, init: Any, target: str, result: Any) -> None:
    lossy = [e for e in result.report.entries if e.severity == "lossy"]
    print(
        f"[mcp-schema-bridge] {target}: {len(result.tools)} tool(s) served, {len(result.rejected)} rejected, "
        f"{len(lossy)} lossy change(s)",
        file=log,
    )
    for r in result.rejected:
        reasons = "; ".join(e.message for e in r.reasons)
        print(f"[mcp-schema-bridge]   rejected {r.name}: {reasons}", file=log)
    log.flush()
