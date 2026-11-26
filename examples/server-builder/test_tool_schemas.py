"""CI gate for an MCP server: every tool must be usable on every model API.

Run with:  uv run --with "mcp-schema-bridge" --with "mcp>=2.3" --with pytest pytest test_tool_schemas.py
"""

import asyncio

import pytest

from crm_server import server
from mcp_schema_bridge import TARGETS, normalize_tools

TOOLS = asyncio.run(server.list_tools())  # MCP SDK Tool objects are accepted as-is


@pytest.mark.parametrize("target", TARGETS)
def test_no_tool_is_rejected(target: str) -> None:
    result = normalize_tools(TOOLS, target)
    problems = {r.name: [e.message for e in r.reasons] for r in result.rejected}
    assert problems == {}, f"{target}: {problems}"


@pytest.mark.parametrize("target", ["openai-strict", "anthropic-strict"])
def test_no_unexpected_lossy_changes(target: str) -> None:
    # Constraints the model may ignore are fine as long as the handler validates them;
    # list them here explicitly so new ones show up in review.
    allowed = {"minLength", "maxLength", "pattern", "minimum", "maximum"}
    result = normalize_tools(TOOLS, target)
    lossy = {e.keyword for e in result.report.entries if e.severity == "lossy"}
    assert lossy <= allowed, f"{target}: unexpected lossy changes {lossy - allowed}"
