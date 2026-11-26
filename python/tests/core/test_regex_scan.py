import json
from pathlib import Path

import pytest

from mcp_schema_bridge.core.regex_scan import scan

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "regex-vectors.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["pattern"])
def test_vectors(vector: dict[str, object]) -> None:
    assert sorted(scan(str(vector["pattern"]))) == sorted(vector["features"])  # type: ignore[arg-type]
