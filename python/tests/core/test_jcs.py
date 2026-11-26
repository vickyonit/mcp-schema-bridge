"""RFC 8785 (JSON Canonicalization Scheme) conformance."""

import json
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcp_schema_bridge.core.jcs import canonicalize


def test_rfc8785_section_3_2_4_example() -> None:
    # RFC 8785 §3.2.4 input, parsed then canonicalized.
    source = (
        '{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],'
        '"string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
        '"literals": [null, true, false]}'
    )
    expected = (
        '{"literals":[null,true,false],'
        '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert canonicalize(json.loads(source)) == expected


def test_rfc8785_section_3_2_3_key_sorting_uses_utf16_code_units() -> None:
    obj = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    keys = list(json.loads(canonicalize(obj)).keys())
    assert keys == ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (9007199254740992.0, "9007199254740992"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
        (4.35, "4.35"),
        (-1.5, "-1.5"),
        (123e-20, "1.23e-18"),
        (1.0, "1"),
        (1, "1"),
        (-42, "-42"),
        (2**53 - 1, "9007199254740991"),
    ],
)
def test_number_serialization_follows_ecmascript(value: float, expected: str) -> None:
    assert canonicalize(value) == expected


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_numbers(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonicalize(bad)


def test_rejects_integers_outside_ijson_range() -> None:
    with pytest.raises(ValueError, match="2\\*\\*53"):
        canonicalize(2**53)


def test_rejects_lone_surrogates() -> None:
    with pytest.raises(ValueError, match="surrogate"):
        canonicalize("\ud800")


def test_bool_is_not_treated_as_number() -> None:
    assert canonicalize([True, False]) == "[true,false]"


def test_control_characters_use_short_escapes_or_lowercase_hex() -> None:
    assert canonicalize("\b\t\n\f\r\x00\x1f") == '"\\b\\t\\n\\f\\r\\u0000\\u001f"'


def test_rejects_non_string_keys() -> None:
    with pytest.raises(TypeError):
        canonicalize({1: "x"})


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_number_formatting_round_trips(x: float) -> None:
    assert float(canonicalize(x)) == x
