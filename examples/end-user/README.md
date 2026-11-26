# Example: an MCP server breaks gemini-cli, and the proxy fixes it without changing either side

`geo_server.py` is a third-party MCP server written the way older JSON Schema generators emit
schemas: a draft-07 tuple for coordinates and a mixed-type enum.

**Before** (`before/.gemini/settings.json`): `gemini-cli` connects, then every request fails:

```
Error when talking to Gemini API ... 400 INVALID_ARGUMENT:
"schema at properties.from.items must be a boolean or an object"
```

**After** (`after/.gemini/settings.json`): the same server, launched through the proxy:

```json
"geo": {
  "command": "uvx",
  "args": ["--from", "mcp-schema-bridge[cli]", "mcp-schema-bridge", "proxy", "--target", "gemini-json",
           "--", "uv", "run", "-q", "--script", "../geo_server.py"]
}
```

```
$ gemini -p "How far is Paris (48.8566, 2.3522) from London (51.5072, -0.1276)? Use the distance tool."
The distance between Paris and London is 343.5 km.
```

The committed `after/` config runs the proxy from this repository (`uv run --project ../../../python`)
so it works before the package is published. Add `--report bridge-report.json` to see every change
the proxy made.

> In headless mode (`gemini -p`) gemini-cli only offers tools it can run without asking, so these
> configs set `"trust": true` for this one local server. In the interactive UI, leave it off and
> approve calls as usual.
