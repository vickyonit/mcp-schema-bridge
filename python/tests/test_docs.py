"""README and docs stay truthful: snippets run, generated sections are current, links resolve."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
README = (REPO / "README.md").read_text(encoding="utf-8")


def _python_blocks(text: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", text, flags=re.S)


@pytest.mark.parametrize("block", _python_blocks(README), ids=lambda b: b.splitlines()[0][:40])
def test_readme_python_snippets_run(block: str) -> None:
    exec(compile(block, "README.md", "exec"), {})


def test_readme_matrix_is_current() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "gen_matrix.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_package_readme_matches_repo_readme() -> None:
    assert (REPO / "python" / "README.md").read_text(encoding="utf-8") == README


def test_relative_links_resolve() -> None:
    for doc in [REPO / "README.md", *REPO.glob("docs/*.md"), REPO / "CONTRIBUTING.md"]:
        for link in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", doc.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            assert (doc.parent / link).exists(), f"{doc.relative_to(REPO)} links to missing {link}"


def test_every_emitted_rule_id_is_documented() -> None:
    catalog = (REPO / "docs" / "rules.md").read_text(encoding="utf-8")
    emitted: set[str] = set()
    for p in (REPO / "corpus" / "expected").rglob("*.json"):
        for e in json.loads(p.read_text(encoding="utf-8"))["report"]["entries"]:
            emitted.add(
                re.sub(
                    r"^(gemini-json|openai-strict|openai|anthropic-strict|anthropic)/",
                    "<target>/",
                    e["rule"],
                )
            )
    missing = sorted(r for r in emitted if f"`{r}`" not in catalog)
    assert missing == []


@pytest.mark.parametrize("path", sorted((REPO / "examples").glob("*.py")), ids=lambda p: p.name)
def test_examples_compile(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_typescript_fix_catalog_matches_python() -> None:
    from mcp_schema_bridge.fixes import FIXES

    ts = (REPO / "typescript" / "src" / "core" / "fixes.ts").read_text(encoding="utf-8")
    body = ts[ts.index("= {") + 2 : ts.index("};") + 1]
    assert json.loads(body) == FIXES
