# Example: checking an MCP server before you ship it

`crm_server.py` is a normal Python MCP server (Pydantic models, optional fields, constraints).

```bash
pip install "mcp-schema-bridge[cli]"

# 1. What happens to each tool on each model API? (exit 1 if any tool is rejected)
mcp-schema-bridge check --stdio -- python crm_server.py

# 2. Gate it in CI
pytest test_tool_schemas.py
```

The first check rejected `create_contact` on `openai-strict` and `anthropic-strict`:

```
[fatal] create_contact  /$defs/Contact/properties/metadata additionalProperties: an object without declared
        properties (a map) cannot be expressed in strict mode (core/open-object-unsupported)
    fix: ... model a map as a list of {key, value} objects (Pydantic: list[KeyValue] instead of dict[str, str]) ...
```

Changing `metadata: dict[str, str]` to `metadata: list[KeyValue]` fixed it for every target.
