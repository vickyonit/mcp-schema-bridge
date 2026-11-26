import pytest

from mcp_schema_bridge.core.pointer import (
    decode_fragment,
    escape_token,
    join,
    split,
    unescape_token,
)


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [("a/b", "a~1b"), ("a~b", "a~0b"), ("~/", "~0~1"), ("~1", "~01"), ("", "")],
)
def test_escape_round_trip(raw: str, escaped: str) -> None:
    assert escape_token(raw) == escaped
    assert unescape_token(escaped) == raw


def test_join_and_split() -> None:
    p = join("", "properties", "a/b", "items")
    assert p == "/properties/a~1b/items"
    assert split(p) == ["properties", "a/b", "items"]
    assert split("") == []


def test_split_rejects_relative_pointer() -> None:
    with pytest.raises(ValueError, match="must start with"):
        split("properties/a")


def test_decode_fragment_percent_decodes_before_unescaping() -> None:
    # "#/$defs/a%25b" -> "/$defs/a%b"; "%7E1" must become "~1" then "/" only via tokens
    assert decode_fragment("#/$defs/a%25b") == ["$defs", "a%b"]
    assert decode_fragment("#/definitions/x~1y") == ["definitions", "x/y"]
    assert decode_fragment("#") == []
    assert decode_fragment("#/a%7E0b") == ["a~b"]
