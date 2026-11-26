#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the wheel, install it into a clean virtualenv and normalize one real corpus tool."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = """
import json, sys
from mcp_schema_bridge import normalize_tools, denormalize_args, __version__, RULES_VERSION
tools = json.load(open(sys.argv[1], encoding="utf-8"))
for target in ("gemini-json", "openai", "openai-strict", "anthropic", "anthropic-strict"):
    res = normalize_tools(tools, target)
    assert res.tools, target
print("ok", __version__, RULES_VERSION, len(tools), "tools")
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        subprocess.run(["uv", "build", "--wheel", "--out-dir", str(t / "dist"), str(ROOT / "python")], check=True, capture_output=True)
        wheel = next((t / "dist").glob("*.whl"))
        subprocess.run(["uv", "venv", "-q", str(t / "venv")], check=True)
        py = t / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(["uv", "pip", "install", "-q", "--python", str(py), str(wheel)], check=True)
        tools = ROOT / "corpus" / "captured" / "server-filesystem" / "tools.json"
        r = subprocess.run([str(py), "-I", "-c", CHECK, str(tools)], cwd=t, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        cli = subprocess.run([str(t / "venv" / ("Scripts" if sys.platform == "win32" else "bin") / "mcp-schema-bridge"), "--version"], capture_output=True, text=True)
        sys.stdout.write(cli.stdout)
        return r.returncode or cli.returncode


if __name__ == "__main__":
    raise SystemExit(main())
