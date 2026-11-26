from mcp_schema_bridge.core.tree import SNode, build, copy_tree, iter_subschemas, to_plain, walk


def test_build_marks_every_subschema_with_its_source_pointer() -> None:
    root = build(
        {
            "type": "object",
            "properties": {"a/b": {"type": "string"}, "title": {"type": "integer"}},
            "anyOf": [{"required": ["a/b"]}],
            "items": {"type": "string"},
            "enum": [{"type": "not-a-schema"}],
            "default": {"properties": {}},
        }
    )
    assert isinstance(root, SNode)
    assert root.src == ("",)
    props = root["properties"]
    assert not isinstance(props, SNode)  # name map, not a schema
    assert props["a/b"].src == ("/properties/a~1b",)
    assert props["title"].src == ("/properties/title",)
    assert root["anyOf"][0].src == ("/anyOf/0",)
    assert root["items"].src == ("/items",)
    assert not isinstance(root["enum"][0], SNode)
    assert not isinstance(root["default"], SNode)


def test_boolean_subschemas_are_left_as_booleans() -> None:
    root = build({"properties": {"a": True}, "additionalProperties": False})
    assert root["properties"]["a"] is True
    assert root["additionalProperties"] is False


def test_walk_yields_pointer_and_node_for_schema_positions_only() -> None:
    root = build(
        {"properties": {"title": {"description": "x"}}, "$defs": {"D": {"type": "string"}}}
    )
    got = [(p, dict(n)) for p, n in walk(root)]
    assert got == [
        ("", dict(root)),
        ("/properties/title", {"description": "x"}),
        ("/$defs/D", {"type": "string"}),
    ]


def test_iter_subschemas_reports_keyword_and_key() -> None:
    root = build({"prefixItems": [{"type": "string"}], "not": {"type": "null"}})
    got = [(kw, key) for kw, key, _ in iter_subschemas(root)]
    assert got == [("prefixItems", 0), ("not", None)]


def test_copy_tree_preserves_provenance_and_ref_targets_but_not_identity() -> None:
    root = build({"properties": {"a": {"type": "string"}}})
    target = root["properties"]["a"]
    ref = SNode({"$ref": "#/properties/a"}, src=("/x",))
    ref.ref = target
    root["properties"]["b"] = ref
    clone = copy_tree(root)
    assert clone is not root
    assert clone["properties"]["a"] is not target
    assert clone["properties"]["a"].src == ("/properties/a",)
    assert clone["properties"]["b"].ref is target  # refs keep pointing at original targets


def test_to_plain_strips_node_types() -> None:
    root = build({"anyOf": [{"type": "string"}], "properties": {"a": True}})
    plain = to_plain(root)
    assert type(plain) is dict
    assert type(plain["anyOf"][0]) is dict
    assert plain == {"anyOf": [{"type": "string"}], "properties": {"a": True}}
