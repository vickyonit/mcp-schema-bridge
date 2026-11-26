"""Minimal stdio MCP server used by CLI tests (paginated tools/list)."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("fake")


@server.tool()
def echo(text: str, times: int | None = None) -> str:
    """Echo text."""
    return text


@server.tool()
def ping() -> str:
    """Ping."""
    return "pong"


if __name__ == "__main__":
    server.run()
