"""Golden corpus (plan §7.1): captured real-server toolsets and synthetic per-transformation cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcp_schema_bridge import (
    Budget,
    NormalizeOptions,
    denormalize_args,
    normalize_schema,
    normalize_tools,
)
from mcp_schema_bridge.core.rules import TARGETS
from tests.support.invariants import check_all, hints_complete

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "corpus"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
STRIP = {"fingerprint", "library_version", "rules_version"}


META: dict[str, dict[str, Any]] = {}


def _cases() -> list[tuple[str, list[dict[str, Any]]]]:
    out: list[tuple[str, list[dict[str, Any]]]] = []
    for d in sorted((CORPUS / "captured").iterdir()):
        out.append((d.name, json.loads((d / "tools.json").read_text(encoding="utf-8"))))
    for f in sorted((CORPUS / "synthetic").glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        name = f"synthetic/{case['id']}"
        out.append((name, case["tools"] if "tools" in case else [case["tool"]]))
        META[name] = case
    return out


CASES = _cases()


def options_for(case: str) -> NormalizeOptions:
    raw = dict(META.get(case, {}).get("options", {}))
    if "reserved_budget" in raw:
        raw["reserved_budget"] = Budget(**raw["reserved_budget"])
    return NormalizeOptions(**raw)


def strip(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: strip(x) for k, x in v.items() if k not in STRIP}
    if isinstance(v, list):
        return [strip(x) for x in v]
    return v


def render(target: str, tools: list[dict[str, Any]], case: str = "") -> str:
    res = normalize_tools(tools, target, options_for(case))  # type: ignore[arg-type]
    out = strip(res.to_dict())
    meta = META.get(case, {})
    if "args" in meta:
        repairs = frozenset(meta.get("repairs", []))
        out["args"] = [
            {
                "tool": t.name,
                "input": a,
                "output": (d := denormalize_args(t, a, repairs=repairs)).args,  # type: ignore[arg-type]
                "warnings": [w.rule for w in d.warnings],
            }
            for t in res.tools
            for a in meta["args"]
        ]
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def golden_path(target: str, case: str) -> Path:
    return CORPUS / "expected" / target / f"{case}.json"


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize(("case", "tools"), CASES, ids=[c for c, _ in CASES])
def test_golden(
    case: str, tools: list[dict[str, Any]], target: str, request: pytest.FixtureRequest
) -> None:
    if case in MANIFEST["pending"]["py"]:
        pytest.xfail("pending in manifest")
    path = golden_path(target, case)
    text = render(target, tools, case)
    if request.config.getoption("--update-golden"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"missing golden {path.relative_to(REPO)}; run pytest --update-golden"
    assert text == path.read_text(encoding="utf-8"), f"golden mismatch for {path.relative_to(REPO)}"


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize(("case", "tools"), CASES, ids=[c for c, _ in CASES])
def test_invariants(case: str, tools: list[dict[str, Any]], target: str) -> None:
    for t in tools:
        r = normalize_schema(t["inputSchema"], target, options_for(case))  # type: ignore[arg-type]
        hinted = hints_complete(r) if options_for(case).hints else []
        assert check_all(t["inputSchema"], r) + hinted == [], t["name"]


def test_coverage_gate() -> None:
    seen: dict[str, set[str]] = {}
    for target in TARGETS:
        for case, _ in CASES:
            path = golden_path(target, case)
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in data["report"]["entries"]:
                seen.setdefault(e["tid"], set()).add(target)
    missing = {
        tid: sorted(set(targets) - seen.get(tid, set()))
        for tid, targets in MANIFEST["coverage"].items()
        if set(targets) - seen.get(tid, set())
    }
    assert missing == {}, f"transformation families not exercised by the corpus: {missing}"


def test_every_captured_source_has_license_metadata() -> None:
    for d in sorted((CORPUS / "captured").iterdir()):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        assert meta.get("license"), d.name
        assert meta.get("source"), d.name
        assert meta.get("version"), d.name


FUZZ = CORPUS / "fuzz" / "cases.jsonl"


def test_fuzz_goldens(request: pytest.FixtureRequest) -> None:
    """Seeded random schemas (scripts/parity_fuzz.py) with Python outputs: a cross-language golden set."""
    if request.config.getoption("--update-golden"):
        import subprocess
        import sys

        FUZZ.parent.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "parity_fuzz.py"), "300", "7"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO / "python",
        ).stdout
        FUZZ.write_text(out, encoding="utf-8")
        return
    for line in filter(None, FUZZ.read_text(encoding="utf-8").split("\n")):
        case = json.loads(line)
        try:
            actual: Any = strip(normalize_tools([case["tool"]], case["target"]).to_dict())
        except Exception as e:
            actual = {"error": type(e).__name__}
        assert json.dumps(actual, ensure_ascii=False) == json.dumps(
            strip(case["expected"]), ensure_ascii=False
        )
