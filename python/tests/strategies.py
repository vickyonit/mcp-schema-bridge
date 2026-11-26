"""Hypothesis strategies for MCP-shaped JSON Schemas (plan §8.2)."""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

HOSTILE_NAMES = [
    "title",
    "$ref",
    "type",
    "a/b",
    "a~b",
    "__proto__",
    "description",
    "properties",
    "x y",
    "ü",
]
NAMES = st.one_of(
    st.sampled_from(["name", "id", "count", "tags", "query", "limit"]),
    st.sampled_from(HOSTILE_NAMES),
)

annotations = st.fixed_dictionaries(
    {},
    optional={
        "description": st.text(min_size=0, max_size=30),
        "title": st.text(min_size=1, max_size=10),
    },
)

string_schema = st.builds(
    lambda base, extra, ann: {"type": "string", **extra, **ann},
    st.just(None),
    st.fixed_dictionaries(
        {},
        optional={
            "minLength": st.integers(0, 5),
            "maxLength": st.integers(5, 50),
            "pattern": st.sampled_from(["^[a-z]+$", "^\\d{3}$", "^(?=a).*$"]),
            "format": st.sampled_from(["date", "date-time", "email", "uri", "uuid", "custom"]),
            "enum": st.lists(st.text(max_size=5), min_size=1, max_size=4, unique=True),
            "default": st.text(max_size=5),
        },
    ),
    annotations,
)

number_schema = st.builds(
    lambda t, extra, ann: {"type": t, **extra, **ann},
    st.sampled_from(["integer", "number"]),
    st.fixed_dictionaries(
        {},
        optional={
            "minimum": st.integers(-10, 0),
            "maximum": st.integers(1, 100),
            "exclusiveMinimum": st.integers(-10, 0),
            "multipleOf": st.sampled_from([1, 2, 5]),
        },
    ),
    annotations,
)

leaf = st.one_of(
    string_schema,
    number_schema,
    st.just({"type": "boolean"}),
    st.builds(lambda c: {"const": c}, st.one_of(st.text(max_size=4), st.integers(0, 9))),
    st.builds(
        lambda e: {"enum": e}, st.lists(st.integers(0, 9), min_size=1, max_size=3, unique=True)
    ),
    st.builds(lambda t: {"type": [t, "null"]}, st.sampled_from(["string", "integer"])),
)


def _extend(children: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    obj = st.builds(
        lambda props, req_mask, extra: {
            "type": "object",
            "properties": props,
            **(
                {"required": [k for k, m in zip(props, req_mask, strict=False) if m]}
                if any(req_mask)
                else {}
            ),
            **extra,
        },
        st.dictionaries(NAMES, children, min_size=1, max_size=4),
        st.lists(st.booleans(), min_size=4, max_size=4),
        st.fixed_dictionaries({}, optional={"additionalProperties": st.booleans()}),
    )
    return st.one_of(
        obj,
        st.builds(
            lambda i, extra: {"type": "array", "items": i, **extra},
            children,
            st.fixed_dictionaries(
                {},
                optional={
                    "minItems": st.integers(0, 2),
                    "maxItems": st.integers(3, 6),
                    "uniqueItems": st.just(True),
                },
            ),
        ),
        st.builds(lambda bs: {"anyOf": bs}, st.lists(children, min_size=2, max_size=3)),
        st.builds(lambda bs: {"oneOf": bs}, st.lists(children, min_size=2, max_size=3)),
        st.builds(lambda bs: {"allOf": bs}, st.lists(children, min_size=2, max_size=3)),
    )


subschema = st.recursive(leaf, _extend, max_leaves=8)


@st.composite
def mcp_schemas(draw: st.DrawFn) -> dict[str, Any]:
    props = draw(st.dictionaries(NAMES, subschema, min_size=0, max_size=5))
    names = list(props)
    required = [n for n in names if draw(st.booleans())]
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    if draw(st.booleans()) and names:
        # move one property into $defs and reference it (sometimes from two places)
        n = names[0]
        schema["$defs"] = {"Shared": props[n]}
        props[n] = {"$ref": "#/$defs/Shared"}
        if len(names) > 1 and draw(st.booleans()):
            props[names[1]] = {"$ref": "#/$defs/Shared"}
    return schema
