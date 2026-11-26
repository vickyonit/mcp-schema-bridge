#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp-schema-bridge"]
#
# [tool.uv.sources]
# mcp-schema-bridge = { path = "../python" }
# ///
"""Record live accept/reject verdicts for every corpus tool, raw and normalized (plan §7.2).

  uv run --script scripts/record_verdicts.py --target gemini-json --model gemini-3.5-flash-lite
  uv run --script scripts/record_verdicts.py --target gemini-json --model ... --check

Writes corpus/verdicts/<target>.json. With --check, nothing is written; the script exits non-zero if
any verdict differs from the committed file or a normalized tool is not accepted.
Each normalized verdict stores the sha256 of the JCS-encoded schema it tested.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers import available, call_tool  # noqa: E402

from mcp_schema_bridge import normalize_tools  # noqa: E402
from mcp_schema_bridge.core.jcs import canonicalize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = {"gemini-json": ("gemini", False), "openai": ("openai", False), "openai-strict": ("openai", True),
            "anthropic": ("anthropic", False), "anthropic-strict": ("anthropic", True)}


def corpus_tools() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for d in sorted((ROOT / "corpus" / "captured").iterdir()):
        for t in json.loads((d / "tools.json").read_text(encoding="utf-8")):
            out.append((f"{d.name}/{t['name']}", t))
    for f in sorted((ROOT / "corpus" / "synthetic").glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        out.append((f"synthetic/{case['id']}", case["tool"]))
    return out


def sha(schema: Any) -> str:
    return hashlib.sha256(canonicalize(schema).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=sorted(PROVIDER))
    ap.add_argument("--model", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    provider, strict = PROVIDER[a.target]
    if not available(provider):
        print(f"skipping: no API key for {provider}", file=sys.stderr)
        return 0
    path = ROOT / "corpus" / "verdicts" / f"{a.target}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"verdicts": {}}
    verdicts: dict[str, Any] = {}
    prompt = "Call the tool once with plausible example arguments."
    for case, tool in corpus_tools():
        res = normalize_tools([tool], a.target)  # type: ignore[arg-type]
        raw = call_tool(provider, model=a.model, schema=tool["inputSchema"], prompt=prompt, strict=strict, tool_name="t")
        entry: dict[str, Any] = {"raw": {"status": raw.status, "error": raw.error}}
        if res.tools:
            nt = res.tools[0]
            norm = call_tool(provider, model=a.model, schema=nt.schema, prompt=prompt, strict=nt.strict, tool_name="t")
            entry["normalized"] = {"status": norm.status, "error": norm.error, "sha256": sha(nt.schema)}
        else:
            entry["normalized"] = {"status": "rejected-by-design", "reasons": [r.rule for r in res.rejected[0].reasons]}
        verdicts[case] = entry
        print(f"{case:55s} raw={raw.status:9s} normalized={entry['normalized']['status']}", flush=True)
    doc = {"target": a.target, "model": a.model,
           "recorded_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "verdicts": verdicts}
    bad = [c for c, v in verdicts.items() if v["normalized"]["status"] not in ("accepted", "rejected-by-design")]
    if a.check:
        drift = [c for c, v in verdicts.items()
                 if old["verdicts"].get(c, {}).get("raw", {}).get("status") != v["raw"]["status"]
                 or old["verdicts"].get(c, {}).get("normalized", {}).get("status") != v["normalized"]["status"]]
        for c in drift:
            print(f"DRIFT {c}", file=sys.stderr)
        for c in bad:
            print(f"NOT ACCEPTED {c}: {verdicts[c]['normalized']}", file=sys.stderr)
        return 1 if (drift or bad) else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in bad:
        print(f"NOT ACCEPTED {c}: {verdicts[c]['normalized']}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
