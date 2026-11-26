"""Golden corpus (plan §7.1): captured real-server toolsets and synthetic per-transformation cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcp_schema_bridge import normalize_schema, normalize_tools
from mcp_schema_bridge.core.rules import TARGETS
from tests.support.invariants import check_all, hints_complete

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "corpus"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text())
STRIP = {"fingerprint", "library_version", "rules_version"}


def _cases() -> list[tuple[str, list[dict[str, Any]]]]:
    out: list[tuple[str, list[dict[str, Any]]]] = []
    for d in sorted((CORPUS / "captured").iterdir()):
        out.append((d.name, json.loads((d / "tools.json").read_text())))
    for f in sorted((CORPUS / "synthetic").glob("*.json")):
        case = json.loads(f.read_text())
        out.append((f"synthetic/{case['id']}", [case["tool"]]))
    return out


CASES = _cases()


def strip(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: strip(x) for k, x in v.items() if k not in STRIP}
    if isinstance(v, list):
        return [strip(x) for x in v]
    return v


def render(target: str, tools: list[dict[str, Any]]) -> str:
    res = normalize_tools(tools, target)  # type: ignore[arg-type]
    return json.dumps(strip(res.to_dict()), indent=2, ensure_ascii=False) + "\n"


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
    text = render(target, tools)
    if request.config.getoption("--update-golden"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return
    assert path.exists(), f"missing golden {path.relative_to(REPO)}; run pytest --update-golden"
    assert text == path.read_text(), f"golden mismatch for {path.relative_to(REPO)}"


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize(("case", "tools"), CASES, ids=[c for c, _ in CASES])
def test_invariants(case: str, tools: list[dict[str, Any]], target: str) -> None:
    for t in tools:
        r = normalize_schema(t["inputSchema"], target)  # type: ignore[arg-type]
        assert check_all(t["inputSchema"], r) + hints_complete(r) == [], t["name"]


def test_coverage_gate() -> None:
    seen: dict[str, set[str]] = {}
    for target in TARGETS:
        for case, _ in CASES:
            path = golden_path(target, case)
            if not path.exists():
                continue
            data = json.loads(path.read_text())
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
        meta = json.loads((d / "meta.json").read_text())
        assert meta.get("license"), d.name
        assert meta.get("source"), d.name
        assert meta.get("version"), d.name
