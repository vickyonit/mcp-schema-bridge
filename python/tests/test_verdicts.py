"""Offline checks of recorded live verdicts (plan §7.2). No API keys needed."""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from pathlib import Path
from typing import Any

import pytest

from mcp_schema_bridge import normalize_tools
from mcp_schema_bridge.core.jcs import canonicalize
from tests.test_corpus import CASES, options_for

VERDICTS = Path(__file__).resolve().parents[2] / "corpus" / "verdicts"
RELEASE = os.environ.get("MSB_RELEASE") == "1"


def _load(target: str) -> dict[str, Any] | None:
    p = VERDICTS / f"{target}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _tools() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for case, tools in CASES:
        for t in tools:
            single = case.startswith("synthetic/") and len(tools) == 1
            out[case if single else f"{case}/{t['name']}"] = {**t, "__case": case}
    return out


def _norm(tool: dict[str, Any], target: str) -> Any:
    case = tool["__case"]
    clean = {k: v for k, v in tool.items() if k != "__case"}
    return normalize_tools([clean], target, options_for(case))  # type: ignore[arg-type]


@pytest.mark.parametrize("target", ["gemini-json"])
def test_verdicts_cover_every_corpus_tool(target: str) -> None:
    doc = _load(target)
    assert doc is not None
    assert set(doc["verdicts"]) == set(_tools())


@pytest.mark.parametrize("target", ["gemini-json"])
def test_normalized_outputs_were_verified_live(target: str) -> None:
    doc = _load(target)
    assert doc is not None
    unverified: list[str] = []
    for case, tool in _tools().items():
        v = doc["verdicts"][case]["normalized"]
        res = _norm(tool, target)
        if not res.tools:
            assert v["status"] == "rejected-by-design", case
            continue
        assert v["status"] == "accepted", (case, v)
        digest = hashlib.sha256(canonicalize(res.tools[0].schema).encode()).hexdigest()
        if digest != v["sha256"]:
            unverified.append(case)
    if unverified:
        msg = f"normalized output changed since live verification for: {unverified}; re-run scripts/record_verdicts.py"
        if RELEASE:
            pytest.fail(msg)
        warnings.warn(msg, stacklevel=1)


@pytest.mark.parametrize("target", ["gemini-json"])
def test_raw_rejections_are_explained_by_the_report(target: str) -> None:
    doc = _load(target)
    assert doc is not None
    for case, tool in _tools().items():
        if doc["verdicts"][case]["raw"]["status"] == "rejected":
            res = _norm(tool, target)
            assert res.report.entries, (
                f"{case} was rejected live but the normalizer changed nothing"
            )
