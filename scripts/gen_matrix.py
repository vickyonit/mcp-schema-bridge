#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the README compatibility matrix from rules/*.json (or --check that it is current)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["gemini-json", "openai", "openai-strict", "anthropic", "anthropic-strict"]
KEYWORDS = [
    "type", "enum", "const", "anyOf", "oneOf", "allOf", "not", "$ref", "pattern", "format",
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "prefixItems", "default",
]
SYMBOL = {"enforced": "✅", "accepted": "☑️", "stripped": "⚠️", "rejected": "❌", None: "–", "rewritten": "🔁"}
START, END = "<!-- matrix:start -->", "<!-- matrix:end -->"


def render() -> str:
    rules = {t: json.loads((ROOT / "rules" / f"{t}.json").read_text()) for t in TARGETS}
    version = json.loads((ROOT / "rules" / "index.json").read_text())["rules_version"]
    lines = [START, "", f"_Generated from `rules/*.json` (rules_version `{version}`) by `scripts/gen_matrix.py`._", ""]
    lines.append("| Target | API field | Strict | Evidence | Verified on |")
    lines.append("|---|---|---|---|---|")
    for t in TARGETS:
        r = rules[t]
        kinds: dict[str, int] = {}
        for e in r["evidence"]:
            kinds[e["evidence"]] = kinds.get(e["evidence"], 0) + 1
        ev = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        dates = sorted({e["verified_on"] for e in r["evidence"]})
        lines.append(f"| `{t}` | `{r['api_field']}` | {'yes' if r['strict'] else 'no'} | {ev} | {dates[-1]} |")
    lines += ["", "| Keyword | " + " | ".join(f"`{t}`" for t in TARGETS) + " |", "|---|" + "---|" * len(TARGETS)]
    for kw in KEYWORDS:
        cells = []
        for t in TARGETS:
            r = rules[t]
            status = r["keywords"].get(kw)
            if status is None and r["unknown_keywords"] == "keep":
                status = "accepted"
            f = r["features"]
            const_unenforced = status in ("stripped", "rejected", None) and r["keywords"].get("enum") in ("enforced", "accepted")
            if (kw == "oneOf" and not f["oneof"]) or (kw == "allOf" and f["merge_allof"]) or (kw == "const" and const_unenforced):
                status = "rewritten"
            cells.append(SYMBOL[status])
        lines.append(f"| `{kw}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        "✅ enforced on generated arguments · ☑️ accepted (kept; enforcement not guaranteed) · "
        "🔁 rewritten to a supported form (`oneOf`→`anyOf`, `allOf` merged, `const`→`enum`) · "
        "⚠️ accepted but silently ignored (removed and restated as a description hint) · "
        "❌ rejected by the API (rewritten or removed with a hint) · – not supported (removed with a hint)",
        "",
        END,
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    readme = ROOT / "README.md"
    text = readme.read_text()
    start, end = text.index(START), text.index(END) + len(END)
    new = text[:start] + render() + text[end:]
    if "--check" in argv:
        if new != text:
            print("README matrix is out of date: run uv run --script scripts/gen_matrix.py", file=sys.stderr)
            return 1
        return 0
    readme.write_text(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
