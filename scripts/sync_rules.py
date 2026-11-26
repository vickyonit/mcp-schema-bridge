#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Copy rules/*.json and spec/keyword-classes.json into each package (or --check they match)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTS = [ROOT / "python" / "src" / "mcp_schema_bridge" / "_rules"]


def sources() -> dict[str, bytes]:
    files = {p.name: p.read_bytes() for p in sorted((ROOT / "rules").glob("*.json"))}
    files["keyword-classes.json"] = (ROOT / "spec" / "keyword-classes.json").read_bytes()
    return files


def main(argv: list[str]) -> int:
    check = "--check" in argv
    src = sources()
    problems: list[str] = []
    for dest in DESTS:
        existing = {p.name for p in dest.glob("*.json")} if dest.exists() else set()
        for name, data in src.items():
            target = dest / name
            if check:
                if not target.exists() or target.read_bytes() != data:
                    problems.append(f"{target.relative_to(ROOT)} is out of sync")
            else:
                dest.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        for stale in existing - set(src):
            if check:
                problems.append(f"{(dest / stale).relative_to(ROOT)} has no source")
            else:
                (dest / stale).unlink()
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print("run: uv run --script scripts/sync_rules.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
