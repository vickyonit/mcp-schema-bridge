#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the Python wheel and sdist and check their contents.

Required: package code, rules data, py.typed, LICENSE, NOTICE. Forbidden: corpus/evidence/tests data.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL = [
    "mcp_schema_bridge/__init__.py",
    "mcp_schema_bridge/py.typed",
    "mcp_schema_bridge/_rules/gemini-json.json",
    "mcp_schema_bridge/_rules/openai-strict.json",
    "mcp_schema_bridge/_rules/anthropic-strict.json",
    "mcp_schema_bridge/_rules/keyword-classes.json",
    "mcp_schema_bridge/_rules/index.json",
]
FORBIDDEN = ("corpus/", "evidence/", "captured/", "expected/", ".env")


def build(out: Path) -> None:
    subprocess.run(["uv", "build", "--out-dir", str(out), str(ROOT / "python")], check=True, capture_output=True)


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        build(out)
        wheel = next(out.glob("*.whl"))
        sdist = next(out.glob("*.tar.gz"))
        names = zipfile.ZipFile(wheel).namelist()
        for req in REQUIRED_WHEEL:
            if req not in names:
                problems.append(f"wheel is missing {req}")
        if not any(n.endswith("licenses/LICENSE") for n in names):
            problems.append("wheel is missing LICENSE")
        if not any(n.endswith("licenses/NOTICE") for n in names):
            problems.append("wheel is missing NOTICE")
        snames = tarfile.open(sdist).getnames()
        for n in [*names, *snames]:
            if any(f in n for f in FORBIDDEN):
                problems.append(f"package contains forbidden path {n}")
        print(f"{wheel.name}: {len(names)} files; {sdist.name}: {len(snames)} files")
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
