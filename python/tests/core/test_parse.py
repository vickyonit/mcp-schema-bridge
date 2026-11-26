import pytest

from mcp_schema_bridge.core.errors import (
    InvalidInputError,
    LimitExceededError,
    SchemaBridgeError,
)
from mcp_schema_bridge.core.parse import Limits, check_value, loads


def test_loads_parses_valid_json() -> None:
    assert loads('{"type": "object", "properties": {}}') == {"type": "object", "properties": {}}


def test_loads_rejects_duplicate_keys_with_pointer() -> None:
    with pytest.raises(InvalidInputError, match="duplicate key 'a'") as exc:
        loads('{"properties": {"a": {}, "a": {}}}')
    assert exc.value.pointer == "/properties"


@pytest.mark.parametrize("text", ["NaN", "[Infinity]", '{"a": -Infinity}'])
def test_loads_rejects_non_finite(text: str) -> None:
    with pytest.raises(InvalidInputError, match="finite"):
        loads(text)


def test_loads_rejects_malformed_json() -> None:
    with pytest.raises(InvalidInputError, match="invalid JSON"):
        loads("{")


def test_check_value_rejects_lone_surrogate_in_key_and_value() -> None:
    with pytest.raises(InvalidInputError, match="surrogate") as exc:
        check_value({"properties": {"x": {"description": "\ud800"}}})
    assert exc.value.pointer == "/properties/x/description"
    with pytest.raises(InvalidInputError, match="surrogate"):
        check_value({"\udc00": 1})


def test_check_value_big_int_reject_by_default() -> None:
    with pytest.raises(InvalidInputError, match="2\\*\\*53") as exc:
        check_value({"maximum": 9223372036854775807})
    assert exc.value.pointer == "/maximum"


def test_check_value_big_int_round_returns_coerced_pointers() -> None:
    value, coerced = check_value({"maximum": 9223372036854775807}, big_int="round")
    assert value == {"maximum": 9.223372036854776e18}
    assert coerced == ["/maximum"]


def test_check_value_returns_deep_copy() -> None:
    original = {"properties": {"a": {"type": "string"}}}
    copy, _ = check_value(original)
    assert copy == original
    assert copy["properties"] is not original["properties"]


def test_check_value_rejects_unsupported_python_types() -> None:
    with pytest.raises(InvalidInputError, match="not a JSON value"):
        check_value({"default": {1, 2}})


def test_limits_max_depth() -> None:
    deep: dict[str, object] = {}
    node = deep
    for _ in range(10):
        child: dict[str, object] = {}
        node["items"] = child
        node = child
    with pytest.raises(LimitExceededError, match="max_depth"):
        check_value(deep, limits=Limits(max_depth=5, max_nodes=1000))


def test_limits_max_nodes() -> None:
    with pytest.raises(LimitExceededError, match="max_nodes"):
        check_value({"enum": list(range(50))}, limits=Limits(max_depth=10, max_nodes=20))


def test_errors_share_base_class() -> None:
    assert issubclass(InvalidInputError, SchemaBridgeError)
    assert issubclass(LimitExceededError, SchemaBridgeError)
