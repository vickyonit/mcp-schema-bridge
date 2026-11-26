"""Command line interface: ``mcp-schema-bridge check|normalize``.

Exit codes: 0 ok, 1 --fail-on threshold reached (check), 2 usage error, 3 input/server/timeout error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

from mcp_schema_bridge._version import __version__
from mcp_schema_bridge.core.errors import SchemaBridgeError
from mcp_schema_bridge.core.options import NormalizeOptions
from mcp_schema_bridge.core.parse import loads
from mcp_schema_bridge.core.report import SEVERITIES, Severity, severity_at_least
from mcp_schema_bridge.core.rules import TARGETS, Target
from mcp_schema_bridge.core.toolset import ToolsetResult, normalize_tools


class _UsageError(Exception):
    pass


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _parser() -> argparse.ArgumentParser:
    p = _ArgParser(
        prog="mcp-schema-bridge", description="Normalize MCP tool schemas for model APIs."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_ in (
        ("normalize", "print normalized tools as JSON"),
        ("check", "report what would change"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument(
            "input",
            nargs="?",
            help="JSON file (a schema, a tool array or a tools/list result); '-' for stdin",
        )
        sp.add_argument(
            "--target", action="append", choices=TARGETS, help="repeatable; default: all targets"
        )
        sp.add_argument(
            "--format", choices=("text", "json"), default="json" if name == "normalize" else "text"
        )
        sp.add_argument(
            "--no-hints",
            action="store_true",
            help="do not restate dropped constraints in descriptions",
        )
        sp.add_argument(
            "--strict-fallback",
            action="store_true",
            help="demote unfixable tools to the non-strict sibling target",
        )
        sp.add_argument(
            "--timeout", type=float, default=60.0, help="seconds to wait for a --stdio server"
        )
        sp.add_argument(
            "--stdio",
            action="store_true",
            help="read tools from an MCP server started from the argv after --",
        )
        if name == "check":
            sp.add_argument(
                "--fail-on",
                choices=SEVERITIES,
                default="fatal",
                help="exit 1 if any entry is at or above this severity",
            )
    pp = sub.add_parser(
        "proxy", help="serve another MCP server's tools with schemas normalized for one target"
    )
    pp.add_argument("--target", required=True, choices=TARGETS)
    pp.add_argument("--no-hints", action="store_true")
    pp.add_argument(
        "--strict-fallback",
        action="store_true",
        help="serve unfixable tools in non-strict form instead of hiding them",
    )
    pp.add_argument(
        "--report", metavar="FILE", help="write the normalization report (JSON) to FILE"
    )
    return p


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, []


def _tools_from_value(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(cast(dict[str, Any], value).get("tools"), list):
        return cast(list[dict[str, Any]], value["tools"])
    if isinstance(value, list):
        return cast(list[dict[str, Any]], value)
    if isinstance(value, dict) and "inputSchema" in value:
        return [cast(dict[str, Any], value)]
    if isinstance(value, dict):
        return [{"name": "schema", "inputSchema": value}]
    raise SchemaBridgeError("input must be a JSON object or array")


def _read_input(path: str) -> list[dict[str, Any]]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return _tools_from_value(loads(text))


async def _list_tools(argv: list[str]) -> list[dict[str, Any]]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.types import PaginatedRequestParams
    except ImportError as e:  # pragma: no cover - depends on installed extras
        raise SchemaBridgeError(
            "--stdio needs the 'cli' extra: pip install 'mcp-schema-bridge[cli]'"
        ) from e
    params = StdioServerParameters(command=argv[0], args=argv[1:])
    tools: list[dict[str, Any]] = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        cursor: str | None = None
        while True:
            page = PaginatedRequestParams(cursor=cursor) if cursor else None
            res: Any = await session.list_tools(params=page)
            for t in cast(list[Any], res.tools):
                d = cast(
                    dict[str, Any], t.model_dump(mode="json", by_alias=True, exclude_none=True)
                )
                tools.append({k: d[k] for k in ("name", "description", "inputSchema") if k in d})
            cursor = cast(str | None, res.next_cursor)
            if not cursor:
                return tools


def _payload(results: dict[str, ToolsetResult]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for target, r in results.items():
        d = r.to_dict()
        out[target] = {"tools": d["tools"], "rejected": d["rejected"], "report": d["report"]}
    return out


def _text(results: dict[str, ToolsetResult]) -> str:
    lines: list[str] = []
    for target, r in results.items():
        counts = {s: 0 for s in SEVERITIES}
        for e in r.report.entries:
            counts[e.severity] += 1
        summary = ", ".join(f"{n} {s}" for s, n in counts.items() if n) or "no changes"
        lines.append(f"{target}: {len(r.tools)} tool(s) ok, {len(r.rejected)} rejected; {summary}")
        for e in r.report.sorted():
            if e.severity == "info":
                continue
            where = f"{e.tool or ''}{e.source_path or '/'}"
            lines.append(f"  [{e.severity}] {where} {e.keyword or ''}: {e.message} ({e.rule})")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args_list, server_argv = _split_argv(list(sys.argv[1:] if argv is None else argv))
    try:
        a = _parser().parse_args(args_list)
        if a.command == "proxy":
            if not server_argv:
                raise _UsageError("proxy needs the upstream server command after --")
            from mcp_schema_bridge.proxy import run_proxy

            opts = NormalizeOptions(hints=not a.no_hints, strict_fallback=a.strict_fallback)
            try:
                asyncio.run(run_proxy(server_argv, a.target, opts, report_path=a.report))
            except (OSError, SchemaBridgeError, ExceptionGroup) as e:
                print(f"mcp-schema-bridge: proxy error: {e}", file=sys.stderr)
                return 3
            return 0
        if a.stdio and not server_argv:
            raise _UsageError("--stdio needs a server command after --")
        if not a.stdio and a.input is None:
            raise _UsageError("missing input (a file path or '-'), or use --stdio -- <command>")
    except _UsageError as e:
        print(f"mcp-schema-bridge: error: {e}", file=sys.stderr)
        return 2
    try:
        if a.stdio:
            tools = asyncio.run(asyncio.wait_for(_list_tools(server_argv), timeout=a.timeout))
        else:
            tools = _read_input(a.input)
        targets: list[Target] = a.target or list(TARGETS)
        opts = NormalizeOptions(hints=not a.no_hints, strict_fallback=a.strict_fallback)
        results = {t: normalize_tools(tools, t, opts) for t in targets}
    except (OSError, SchemaBridgeError, TimeoutError, ExceptionGroup, ValueError) as e:
        print(f"mcp-schema-bridge: error: {e}", file=sys.stderr)
        return 3
    if a.format == "json":
        sys.stdout.write(json.dumps(_payload(results), indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_text(results))
    if a.command == "check":
        threshold = cast(Severity, a.fail_on)
        worst = any(
            severity_at_least(e.severity, threshold)
            for r in results.values()
            for e in r.report.entries
        )
        return 1 if worst else 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
