#!/usr/bin/env python3
"""Differential fuzzing input: random MCP-shaped schemas with the Python reference output.

  cd python && uv run python ../scripts/parity_fuzz.py 300 > ../typescript/fuzz-cases.jsonl
  cd ../typescript && MSB_FUZZ_FILE=fuzz-cases.jsonl npx vitest run test/parity-fuzz.test.ts

Each line: {"target", "schema", "expected": ordered Python output (to_dict of normalize_tools) or
{"error": "<ExceptionClass>"}}.
"""

from __future__ import annotations

import json
import random
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from hypothesis.errors import NonInteractiveExampleWarning  # noqa: E402

from mcp_schema_bridge import TARGETS, SchemaBridgeError, normalize_tools  # noqa: E402
from tests.strategies import mcp_schemas  # noqa: E402

warnings.simplefilter("ignore", NonInteractiveExampleWarning)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    strategy = mcp_schemas()
    for _ in range(n):
        schema = strategy.example()
        target = rng.choice(TARGETS)
        tool = {"name": "fuzz", "inputSchema": schema}
        try:
            expected = normalize_tools([tool], target).to_dict()
        except SchemaBridgeError as e:
            expected = {"error": type(e).__name__}
        print(json.dumps({"target": target, "tool": tool, "expected": expected}, ensure_ascii=False))


if __name__ == "__main__":
    main()
