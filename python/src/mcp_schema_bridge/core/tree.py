"""Internal schema tree.

Every *schema object* is an :class:`SNode` (a ``dict`` subclass) carrying:

- ``src``: the source pointer(s) it came from in the original input (provenance trace);
- ``ref``: for nodes holding ``$ref``, the resolved target node (identity, so refs survive moves);
- ``ops``: reverse-map operations anchored at this node.

Non-schema containers (the ``properties`` name map, ``enum`` values, ``default`` values, ...) stay
plain ``dict``/``list`` objects, so property names are never confused with keywords.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from mcp_schema_bridge.core.pointer import join

SCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
SCHEMA_ARRAYS = ("allOf", "anyOf", "oneOf", "prefixItems")
SCHEMA_VALUES = (
    "additionalProperties",
    "propertyNames",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "unevaluatedProperties",
    "unevaluatedItems",
    "additionalItems",
    "contentSchema",
)

Schema = Any  # SNode | bool


class SNode(dict[str, Any]):
    __slots__ = ("kw_src", "ops", "ref", "src")

    def __init__(
        self, *args: Any, src: tuple[str, ...] = (), ref: SNode | None = None, **kw: Any
    ) -> None:
        super().__init__(*args, **kw)
        self.src: tuple[str, ...] = src
        self.ref: SNode | None = ref
        self.ops: list[dict[str, Any]] = []
        self.kw_src: dict[str, tuple[str, ...]] = {}
        """Per-keyword origin when a keyword came from a different source node (allOf merges)."""

    def origins(self, keyword: str) -> tuple[str, ...]:
        """Source pointer(s) that contributed ``keyword``'s current value."""
        return self.kw_src.get(keyword, (self.src[0],) if self.src else ("",))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SNode({super().__repr__()}, src={self.src})"


class Seen:
    """Identity set of nodes that keeps them alive (``id()`` values are reused after GC)."""

    __slots__ = ("_nodes",)

    def __init__(self) -> None:
        self._nodes: dict[int, Any] = {}

    def __contains__(self, node: object) -> bool:
        return self._nodes.get(id(node)) is node

    def add(self, node: object) -> None:
        self._nodes[id(node)] = node


def is_schema(value: Any) -> bool:
    return isinstance(value, SNode | bool)


def build(value: Any, pointer: str = "") -> Any:
    """Convert a plain JSON schema (already validated by S0) into an SNode tree."""
    if isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        return value
    raw = cast(dict[str, Any], value)
    node = SNode(src=(pointer,))
    for kw, v in raw.items():
        node[kw] = _build_child(kw, v, join(pointer, kw))
    return node


def _build_child(kw: str, v: Any, pointer: str) -> Any:
    if kw in SCHEMA_MAPS and isinstance(v, dict):
        return {k: build(s, join(pointer, k)) for k, s in cast(dict[str, Any], v).items()}
    if kw in SCHEMA_ARRAYS and isinstance(v, list):
        return [build(s, join(pointer, i)) for i, s in enumerate(cast(list[Any], v))]
    if kw in SCHEMA_VALUES:
        return build(v, pointer)
    if kw == "items":
        if isinstance(v, list):  # draft-07 tuple form
            return [build(s, join(pointer, i)) for i, s in enumerate(cast(list[Any], v))]
        return build(v, pointer)
    if kw == "dependencies" and isinstance(v, dict):
        return {
            k: (build(s, join(pointer, k)) if isinstance(s, dict | bool) else s)
            for k, s in cast(dict[str, Any], v).items()
        }
    return _plain_copy(v)


def _plain_copy(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _plain_copy(x) for k, x in cast(dict[str, Any], v).items()}
    if isinstance(v, list):
        return [_plain_copy(x) for x in cast(list[Any], v)]
    return v


def iter_subschemas(node: SNode) -> Iterator[tuple[str, str | int | None, Schema]]:
    """Yield ``(keyword, key_or_index_or_None, subschema)`` for each direct subschema."""
    for kw, v in node.items():
        if kw in SCHEMA_MAPS and isinstance(v, dict):
            for k, s in cast(dict[str, Any], v).items():
                if is_schema(s):
                    yield kw, k, s
        elif (kw in SCHEMA_ARRAYS or kw == "items") and isinstance(v, list):
            for i, s in enumerate(cast(list[Any], v)):
                if is_schema(s):
                    yield kw, i, s
        elif (kw in SCHEMA_VALUES or kw == "items") and is_schema(v):
            yield kw, None, v
        elif kw == "dependencies" and isinstance(v, dict):
            for k, s in cast(dict[str, Any], v).items():
                if is_schema(s):
                    yield kw, k, s


def child_pointer(pointer: str, kw: str, key: str | int | None) -> str:
    return join(pointer, kw) if key is None else join(pointer, kw, key)


def walk(node: Schema, pointer: str = "") -> Iterator[tuple[str, SNode]]:
    """Pre-order traversal of SNodes (booleans are skipped). Does not follow ``$ref``."""
    if not isinstance(node, SNode):
        return
    yield pointer, node
    for kw, key, child in iter_subschemas(node):
        yield from walk(child, child_pointer(pointer, kw, key))


def copy_tree(node: Schema) -> Any:
    """Deep copy, preserving ``src``/``ops`` and keeping ``ref`` pointing at the original target."""
    if not isinstance(node, SNode):
        return node
    out = SNode(src=node.src, ref=node.ref)
    out.ops = [dict(op) for op in node.ops]
    out.kw_src = dict(node.kw_src)
    for kw, v in node.items():
        if kw in SCHEMA_MAPS and isinstance(v, dict):
            out[kw] = {k: copy_tree(s) for k, s in cast(dict[str, Any], v).items()}
        elif (kw in SCHEMA_ARRAYS or kw == "items") and isinstance(v, list):
            out[kw] = [copy_tree(s) for s in cast(list[Any], v)]
        elif (kw in SCHEMA_VALUES or kw == "items") and is_schema(v):
            out[kw] = copy_tree(v)
        elif kw == "dependencies" and isinstance(v, dict):
            out[kw] = {k: copy_tree(s) for k, s in cast(dict[str, Any], v).items()}
        else:
            out[kw] = _plain_copy(v)
    return out


def to_plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: to_plain(v) for k, v in cast(dict[str, Any], node).items()}
    if isinstance(node, list):
        return [to_plain(v) for v in cast(list[Any], node)]
    return node
