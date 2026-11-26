import re

import mcp_schema_bridge


def test_exposes_semver_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+([ab]\d+|rc\d+)?", mcp_schema_bridge.__version__)
