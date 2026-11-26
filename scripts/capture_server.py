#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.3"]
# ///
"""Capture `tools/list` from an MCP server over stdio and store it under corpus/captured/<id>/.

Usage:
  uv run --script scripts/capture_server.py --id server-memory --version 2.2.1 \
      --license "Apache-2.0 AND MIT" --source https://github.com/modelcontextprotocol/servers \
      -- npx -y @modelcontextprotocol/server-memory@2.2.1

The command is run as an argv list (never through a shell). Captures are committed, so this only
needs to run when a server is (re-)captured.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import PaginatedRequestParams

ROOT = Path(__file__).resolve().parents[1]


async def capture(argv: list[str]) -> list[dict[str, Any]]:
    params = StdioServerParameters(command=argv[0], args=argv[1:])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            res = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
            for t in res.tools:
                d = t.model_dump(mode="json", by_alias=True, exclude_none=True)
                tools.append({k: d[k] for k in ("name", "description", "inputSchema") if k in d})
            cursor = res.next_cursor
            if not cursor:
                return tools


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--license", required=True, help="SPDX expression")
    ap.add_argument("--source", required=True)
    ap.add_argument("argv", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    argv = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
    if not argv:
        ap.error("missing server command after --")
    tools = asyncio.run(asyncio.wait_for(capture(argv), timeout=180))
    out = ROOT / "corpus" / "captured" / a.id
    out.mkdir(parents=True, exist_ok=True)
    (out / "tools.json").write_text(json.dumps(tools, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Never record local paths (privacy): absolute path arguments are replaced by a placeholder.
    recorded = ["<path>" if arg.startswith("/") or arg[1:3] == ":\\" else arg for arg in argv]
    meta = {
        "id": a.id,
        "source": a.source,
        "version": a.version,
        "license": a.license,
        "command": recorded,
        "captured_on": dt.date.today().isoformat(),
        "tool_count": len(tools),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"captured {len(tools)} tools -> {out.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
