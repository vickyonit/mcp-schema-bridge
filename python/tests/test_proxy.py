"""`mcp-schema-bridge proxy`: serve another MCP server's tools with schemas normalized for a target."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAW = str(Path(__file__).parent / "fixtures" / "raw_server.py")


async def _session_run(proxy_args: list[str], fn: Any) -> Any:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_schema_bridge.cli", "proxy", *proxy_args, "--", sys.executable, RAW],
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        return await fn(s)


def run(proxy_args: list[str], fn: Any) -> Any:
    return anyio.run(_session_run, proxy_args, fn)


def test_lists_tools_with_normalized_schemas_and_drops_rejected_ones() -> None:
    async def fn(s: ClientSession) -> Any:
        return (await s.list_tools()).tools

    tools = run(["--target", "openai-strict"], fn)
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"search", "say"}  # 'tag' (open map) cannot be strict
    schema = by_name["search"].input_schema
    assert schema["required"] == ["query", "limit", "kind"]
    assert schema["properties"]["limit"]["type"] == ["integer", "null"]
    assert schema["additionalProperties"] is False


def test_call_tool_forwards_denormalized_arguments() -> None:
    async def fn(s: ClientSession) -> Any:
        res = await s.call_tool("search", {"query": "lamps", "limit": None, "kind": None})
        return json.loads(res.content[0].text)  # type: ignore[union-attr]

    assert run(["--target", "openai-strict"], fn) == {"query": "lamps"}


def test_strict_fallback_keeps_rejected_tools_non_strict() -> None:
    async def fn(s: ClientSession) -> Any:
        return {t.name for t in (await s.list_tools()).tools}

    assert run(["--target", "openai-strict", "--strict-fallback"], fn) == {"search", "say", "tag"}


def test_gemini_rewrites_const_and_restates_dropped_constraints() -> None:
    async def fn(s: ClientSession) -> Any:
        return {t.name: t.input_schema for t in (await s.list_tools()).tools}

    schemas = run(["--target", "gemini-json"], fn)
    q = schemas["search"]["properties"]
    assert q["kind"]["enum"] == ["web"]
    assert q["query"]["description"] == "[constraints: minLength=1]"


def test_report_file(tmp_path: Path) -> None:
    out = tmp_path / "report.json"

    async def fn(s: ClientSession) -> Any:
        return len((await s.list_tools()).tools)

    run(["--target", "openai-strict", "--report", str(out)], fn)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["target"] == "openai-strict"
    assert [r["name"] for r in report["rejected"]] == ["tag"]


def test_proxy_requires_server_command(capsys: pytest.CaptureFixture[str]) -> None:
    from mcp_schema_bridge.cli import main

    assert main(["proxy", "--target", "gemini-json"]) == 2


def test_proxy_upstream_failure_exits_3() -> None:
    from mcp_schema_bridge.cli import main

    assert (
        main(["proxy", "--target", "openai", "--", sys.executable, "-c", "import sys; sys.exit(1)"])
        == 3
    )
