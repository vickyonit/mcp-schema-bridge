#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge"]
#
# [tool.uv.sources]
# mcp-schema-bridge = { path = "../python", editable = true }
# ///
"""Normalize a 100-tool toolset built from the captured corpus; report p50/p99 per target."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from mcp_schema_bridge import TARGETS, normalize_tools

ROOT = Path(__file__).resolve().parents[1]


def toolset(n: int = 100) -> list[dict]:
    tools: list[dict] = []
    for d in sorted((ROOT / "corpus" / "captured").iterdir()):
        tools += json.loads((d / "tools.json").read_text(encoding="utf-8"))
    out = []
    i = 0
    while len(out) < n:
        t = dict(tools[i % len(tools)])
        t["name"] = f"{t['name']}_{i}"
        out.append(t)
        i += 1
    return out


def main() -> None:
    tools = toolset()
    print(f"{len(tools)} tools (from the captured corpus)\n")
    print("| target | p50 ms | p99 ms |\n|---|---|---|")
    for target in TARGETS:
        runs = []
        for _ in range(30):
            t0 = time.perf_counter()
            normalize_tools(tools, target)
            runs.append((time.perf_counter() - t0) * 1000)
        runs.sort()
        print(f"| `{target}` | {statistics.median(runs):.1f} | {runs[int(len(runs) * 0.99) - 1]:.1f} |")


if __name__ == "__main__":
    main()
