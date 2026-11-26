"""CLI: mcp-schema-bridge check|normalize."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from mcp_schema_bridge.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
TOOLS = [
    {
        "name": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string", "minLength": 1}},
            "required": ["q"],
        },
    },
]


def write(tmp_path: Path, data: Any) -> str:
    p = tmp_path / "in.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_normalize_tools_list_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "normalize",
            write(tmp_path, {"tools": TOOLS}),
            "--target",
            "gemini-json",
            "--target",
            "openai",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(out) == {"gemini-json", "openai"}
    assert out["gemini-json"]["tools"][0]["name"] == "search"
    assert set(out["openai"]) == {"tools", "rejected", "report"}


def test_accepts_bare_tool_array_and_single_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["normalize", write(tmp_path, TOOLS), "--target", "openai"]) == 0
    capsys.readouterr()
    assert main(["normalize", write(tmp_path, TOOLS[0]["inputSchema"]), "--target", "openai"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["openai"]["tools"][0]["name"] == "schema"


def test_check_exit_code_follows_fail_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = write(tmp_path, TOOLS)
    assert main(["check", f, "--target", "gemini-json"]) == 0  # default --fail-on fatal
    assert (
        main(["check", f, "--target", "gemini-json", "--fail-on", "lossy"]) == 1
    )  # minLength not enforced
    assert main(["check", f, "--target", "openai", "--fail-on", "lossy"]) == 0
    text = capsys.readouterr().out
    assert "gemini-json" in text
    assert "lossy" in text


def test_check_worst_result_across_targets(tmp_path: Path) -> None:
    f = write(tmp_path, TOOLS)
    assert (
        main(["check", f, "--target", "openai", "--target", "gemini-json", "--fail-on", "lossy"])
        == 1
    )


def test_check_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["check", write(tmp_path, TOOLS), "--target", "gemini-json", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert out["gemini-json"]["report"]["entries"][0]["keyword"] == "minLength"


def test_stdin_input(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(TOOLS)))
    assert main(["normalize", "-", "--target", "openai"]) == 0
    assert "search" in capsys.readouterr().out


def test_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["normalize", "--target", "openai"]) == 2
    assert main(["bogus"]) == 2
    assert main(["normalize", "x.json", "--target", "nope"]) == 2
    capsys.readouterr()


def test_input_errors_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert main(["normalize", str(bad), "--target", "openai"]) == 3
    assert main(["normalize", str(tmp_path / "missing.json"), "--target", "openai"]) == 3
    assert "invalid JSON" in capsys.readouterr().err


def test_stdio_server(capfd: pytest.CaptureFixture[str]) -> None:
    # capfd (not capsys): the MCP stdio client needs real file descriptors for the child's stderr.
    rc = main(
        [
            "check",
            "--target",
            "openai-strict",
            "--format",
            "json",
            "--stdio",
            "--",
            sys.executable,
            str(FIXTURES / "fake_server.py"),
        ]
    )
    out = json.loads(capfd.readouterr().out)
    assert rc == 0
    assert [t["name"] for t in out["openai-strict"]["tools"]] == ["echo", "ping"]


def test_stdio_server_failure_exits_3(capfd: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "check",
            "--target",
            "openai",
            "--timeout",
            "5",
            "--stdio",
            "--",
            sys.executable,
            "-c",
            "import sys; sys.exit(1)",
        ]
    )
    assert rc == 3
    capfd.readouterr()
