# mcp-schema-bridge

**Make any MCP server's tools callable from Gemini, OpenAI and Anthropic, without silently losing
meaning, and map the model's arguments back to what the MCP server expects.**

[![CI](https://github.com/vickyonit/mcp-schema-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/vickyonit/mcp-schema-bridge/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

MCP servers describe tools with arbitrary JSON Schema. Every model API accepts a *different, moving*
subset of it:

- Some schemas are **rejected outright**. Gemini, for example, returns
  `400 INVALID_ARGUMENT: schema at properties.point.items must be a boolean or an object`
  for draft-07 tuple arrays.
- Some keywords are **accepted and then silently ignored**. Our live probes show Gemini does not
  enforce `const`, `pattern`, `minLength`, `exclusiveMinimum`, `multipleOf`, `uniqueItems` or `not`.
- **Strict modes change the shape.** OpenAI strict makes every property required, so the model sends
  `null` for "not provided". Your MCP server may treat that differently from a missing key.

`mcp-schema-bridge` rewrites each tool schema for the target you pick and handles all three:

1. It produces a schema **the target accepts and enforces as much as possible**. For example, Gemini
   ignores `const` but enforces `enum`, so `const: "x"` becomes `enum: ["x"]`. Gemini also ignores
   `exclusiveMinimum` but enforces `minimum`, so on integers `exclusiveMinimum: 0` becomes `minimum: 1`.
2. It emits a **machine-readable report** of every change, each with a severity
   (`info` · `reversible` · `lossy` · `fatal`) and a stable rule id. Constraints that had to be
   dropped are restated in the field's description, so the model still sees them.
3. It **maps the model's arguments back**: `denormalize_args()` undoes the reversible rewrites, such as
   removing injected `null`s or unwrapping a wrapped root, before you call the MCP server.

Every provider rule is backed by a recorded API response, a live probe, or a documentation citation,
with the date it was verified. The [compatibility matrix](#compatibility-matrix) below is generated
from those rules.

> **Status:** pre-release (`0.x`). Python and TypeScript packages are available from this repository.
> They produce byte-identical output: same schemas, reports, key order and fingerprints, checked on
> the shared corpus and by differential fuzzing in CI.

## Install

```bash
npm install mcp-schema-bridge            # TypeScript / JavaScript (Node >= 22), see typescript/README.md
pip install mcp-schema-bridge            # Python, zero runtime dependencies
pip install "mcp-schema-bridge[sdks]"    # + payload adapters for google-genai / openai / anthropic
pip install "mcp-schema-bridge[cli]"     # + `--stdio` support for the CLI (official MCP SDK)
```

## Quickstart

```python
from mcp_schema_bridge import denormalize_args, normalize_tools

tools = [  # as returned by an MCP server's tools/list
    {
        "name": "search",
        "description": "Search the catalogue",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    }
]

result = normalize_tools(tools, "openai-strict")
search = result.tools[0]
print(search.schema["required"])           # ['query', 'limit']  (strict mode requires every key)
print(search.schema["properties"]["limit"]["type"])   # ['integer', 'null']

for entry in result.report.entries:
    print(entry.severity, entry.rule, entry.source_path, entry.keyword)

# The model omitted `limit` by sending null; the MCP server gets the original shape back:
args = denormalize_args(search, {"query": "lamps", "limit": None}).args
assert args == {"query": "lamps"}
```

Use the result with your provider SDK (requires the `[sdks]` extra):

```python
from mcp_schema_bridge import normalize_tools, to_sdk_payload

tools = [{"name": "ping", "inputSchema": {"type": "object"}}]
gemini_tools = to_sdk_payload(normalize_tools(tools, "gemini-json"), "genai")            # list[types.Tool]
openai_tools = to_sdk_payload(normalize_tools(tools, "openai-strict"), "openai-responses")
claude_tools = to_sdk_payload(normalize_tools(tools, "anthropic-strict"), "anthropic-messages")
```

A complete loop (MCP `list_tools` → normalize → model → `denormalize_args` → `call_tool`) for each
provider is in [`examples/`](examples/).

## CLI

```bash
# What would change for each target? Exits 1 if anything is lossy (useful in CI).
mcp-schema-bridge check tools.json --fail-on lossy

# Check a live MCP server (the command after -- is run as an argv list, never through a shell)
mcp-schema-bridge check --target gemini-json --target openai-strict \
  --stdio -- npx -y @modelcontextprotocol/server-filesystem /tmp

# Print normalized tools + reports as JSON
mcp-schema-bridge normalize tools.json --target anthropic-strict > normalized.json
```

Input can be a single schema, an array of tools, or a `tools/list` result (from a file or `-` for
stdin). Exit codes: `0` ok · `1` `--fail-on` threshold reached · `2` usage error · `3` input, server
or timeout error.

## Targets

| Target | Use it for |
|---|---|
| `gemini-json` | Gemini `FunctionDeclaration.parametersJsonSchema` (google-genai `parameters_json_schema`) |
| `openai` | OpenAI function tools with `strict: false` |
| `openai-strict` | OpenAI function tools with `strict: true` (Structured Outputs) |
| `anthropic` | Claude tools (`input_schema`) |
| `anthropic-strict` | Claude tools with `strict: true` |

Strict targets also enforce per-request budgets (`normalize_tools`). With `strict_fallback=True`, a tool
that cannot be made strict is demoted to the non-strict sibling target instead of being rejected.

## The report

Every change is a `ReportEntry`:

```json
{
  "rule": "openai-strict/optional-to-nullable", "tid": "T11a", "tool": "search",
  "source_path": "/properties/limit", "target_path": "/properties/limit", "instance_path": "/limit",
  "keyword": "type", "action": "rewritten", "severity": "reversible",
  "original": "integer", "hinted": false, "message": "optional property 'limit' made required and nullable; ..."
}
```

| Severity | Meaning |
|---|---|
| `info` | No change in what is accepted (e.g. `$schema` removed, `allOf` merged exactly). |
| `reversible` | The model's contract changed, and `denormalize_args` restores the original exactly. |
| `lossy` | A constraint or distinction is no longer enforced by the target (restated as a hint where possible). |
| `fatal` | The tool cannot be expressed for this target; it is rejected (or demoted with `strict_fallback`). |

`--fail-on lossy` is the recommended CI threshold. The report's JSON Schema is
[`spec/report.schema.json`](spec/report.schema.json), and the hint format is
[`spec/hint-format.md`](spec/hint-format.md).

## Guarantees (tested)

The test suite checks every property below against generated schemas, 10 captured real-world servers
and 24 per-transformation cases:

- **No silent loss.** Every validation keyword of the input either survives unchanged on a traced output
  node or has a report entry.
- **Round-trip.** Any arguments valid for the normalized schema, after `denormalize_args`, are valid for
  the original schema, relaxed only where the report says something was lost.
- **Idempotent and deterministic.** Normalizing the output again changes nothing, and identical input
  always gives byte-identical output.
- **Allow-list.** The output only uses keywords and formats the target's rules allow.

## Performance

Normalizing a 100-tool toolset (built from the captured corpus) takes about **20–25 ms per target** on an
Apple Silicon laptop (`scripts/benchmark.py`, p50; p99 within 2 ms). Output is deterministic, so cache
`NormalizedTool`s (they serialize with `to_dict()`/`from_dict()`) and re-normalize only when a server's
`tools/list` changes. See [docs/framework-authors.md](docs/framework-authors.md).

## What we can't fix

- `oneOf` exclusivity, on targets that only support `anyOf` (reported `lossy` unless the branches are provably disjoint).
- Telling "omitted" from "explicitly null" for fields that were already optional **and** nullable under
  `openai-strict` (reported `lossy`; an opt-in sentinel is planned).
- Open maps (`additionalProperties: {…}`, `{type: object}` without properties) under strict targets (`fatal`).
- Recursion on `anthropic-strict` beyond `max_ref_depth`, and recursion only through required fields
  (which no finite value can satisfy).
- `$dynamicRef` / `$recursiveRef` and remote `$ref`s (never fetched).
- Tool and property names a target forbids (rejected in v0.1; renaming is planned for v0.2).

## Compatibility matrix

<!-- matrix:start -->

_Generated from `rules/*.json` (rules_version `2026.11.26`) by `scripts/gen_matrix.py`._

| Target | API field | Strict | Evidence | Verified on |
|---|---|---|---|---|
| `gemini-json` | `parametersJsonSchema` | no | 1 assumed, 3 doc, 7 probe | 2026-11-26 |
| `openai` | `parameters` | no | 2 doc, 3 reported | 2026-11-26 |
| `openai-strict` | `parameters` | yes | 2 assumed, 7 doc, 2 reported | 2026-11-26 |
| `anthropic` | `input_schema` | no | 2 doc, 2 reported | 2026-11-26 |
| `anthropic-strict` | `input_schema` | yes | 9 doc, 1 reported | 2026-11-26 |

| Keyword | `gemini-json` | `openai` | `openai-strict` | `anthropic` | `anthropic-strict` |
|---|---|---|---|---|---|
| `type` | ✅ | ☑️ | ✅ | ☑️ | ✅ |
| `enum` | ✅ | ☑️ | ✅ | ☑️ | ✅ |
| `const` | 🔁 | ☑️ | 🔁 | ☑️ | ✅ |
| `anyOf` | ✅ | ☑️ | ✅ | ☑️ | ✅ |
| `oneOf` | 🔁 | ☑️ | 🔁 | ☑️ | 🔁 |
| `allOf` | 🔁 | ☑️ | 🔁 | ☑️ | 🔁 |
| `not` | ⚠️ | ☑️ | ❌ | ☑️ | ❌ |
| `$ref` | ✅ | ☑️ | ✅ | ☑️ | ✅ |
| `pattern` | ⚠️ | ☑️ | ✅ | ☑️ | ✅ |
| `format` | ☑️ | ☑️ | ✅ | ☑️ | ✅ |
| `minLength` | ⚠️ | ☑️ | – | ☑️ | ❌ |
| `maxLength` | ⚠️ | ☑️ | – | ☑️ | ❌ |
| `minimum` | ✅ | ☑️ | ✅ | ☑️ | ❌ |
| `maximum` | ✅ | ☑️ | ✅ | ☑️ | ❌ |
| `exclusiveMinimum` | ⚠️ | ☑️ | ✅ | ☑️ | ❌ |
| `multipleOf` | ⚠️ | ☑️ | ✅ | ☑️ | ❌ |
| `minItems` | ✅ | ☑️ | ✅ | ☑️ | ✅ |
| `maxItems` | ✅ | ☑️ | ✅ | ☑️ | ❌ |
| `uniqueItems` | ⚠️ | ☑️ | – | ☑️ | ❌ |
| `prefixItems` | ☑️ | ☑️ | – | ☑️ | – |
| `default` | ☑️ | ☑️ | – | ☑️ | ☑️ |

✅ enforced on generated arguments · ☑️ accepted (kept; enforcement not guaranteed) · 🔁 rewritten to a supported form (`oneOf`→`anyOf`, `allOf` merged, `const`→`enum`) · ⚠️ accepted but silently ignored (removed and restated as a description hint) · ❌ rejected by the API (rewritten or removed with a hint) · – not supported (removed with a hint)

<!-- matrix:end -->

How each cell was established, with links, models and dates, is in [`rules/`](rules/). Gemini rows
come from live probes ([`evidence/`](evidence/)) and recorded verdicts ([`corpus/verdicts/`](corpus/verdicts/)).
OpenAI and Anthropic rows currently cite documentation or community reports. See
[docs/live-verification.md](docs/live-verification.md).

## Related projects

Other libraries also convert tool schemas between providers, including
[`tool-schema`](https://www.npmjs.com/package/tool-schema), [`mcpschema`](https://pypi.org/project/mcpschema/),
[`@mastra/schema-compat`](https://www.npmjs.com/package/@mastra/schema-compat) and the provider SDKs' own
strict-mode helpers. `mcp-schema-bridge` focuses on the report, the argument round-trip and
evidence-backed rules. See [docs/adr/0001-why-this-exists.md](docs/adr/0001-why-this-exists.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The project uses strict TDD, atomic Conventional Commits and the
DCO. Security reports: [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
