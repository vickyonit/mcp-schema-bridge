#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Copy rules/*.json and spec/keyword-classes.json into each package, and README/LICENSE/NOTICE into the
Python project directory (or --check that every copy matches its source)."""

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
    for name in ("README.md", "LICENSE", "NOTICE"):
        src_file, dst_file = ROOT / name, ROOT / "python" / name
        if check:
            if not dst_file.exists() or dst_file.read_bytes() != src_file.read_bytes():
                problems.append(f"python/{name} is out of sync")
        else:
            dst_file.write_bytes(src_file.read_bytes())
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print("run: uv run --script scripts/sync_rules.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
