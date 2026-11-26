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
from tests.test_corpus import CASES

VERDICTS = Path(__file__).resolve().parents[2] / "corpus" / "verdicts"
RELEASE = os.environ.get("MSB_RELEASE") == "1"


def _load(target: str) -> dict[str, Any] | None:
    p = VERDICTS / f"{target}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _tools() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for case, tools in CASES:
        for t in tools:
            out[case if case.startswith("synthetic/") else f"{case}/{t['name']}"] = t
    return out


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
        res = normalize_tools([tool], target)  # type: ignore[arg-type]
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
            res = normalize_tools([tool], target)  # type: ignore[arg-type]
            assert res.report.entries, (
                f"{case} was rejected live but the normalizer changed nothing"
            )
