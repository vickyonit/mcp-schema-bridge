# Persona walkthroughs: friction log

Each persona below was played for real. I followed only the public docs, built the example the way
that persona would, and ran it against live APIs where keys were available. Every friction point
records what was felt, what was changed, and where.

## Persona 1: MCP server builder (Python, Pydantic)

Goal: "Will my CRM server work in Gemini, ChatGPT and Claude before I publish it?"

Steps: wrote `examples/server-builder/crm_server.py` the usual way (Pydantic models, `str | None = None`,
`Literal`, `dict[str, str]` metadata, `Field` constraints). Then ran
`mcp-schema-bridge check --stdio -- uv run -q --script crm_server.py`.

| # | What I felt | Change |
|---|---|---|
| 1.1 | Exit 1 and a `fatal` on `metadata`, but **no hint about what to change in my server**. The message describes the problem ("an object without declared properties (a map)…") but not the fix. | The CLI text output now prints a `fix:` line for each rule that has an actionable server-side fix. `docs/rules.md` gained a "How to fix it in your server" section. |
| 1.2 | The location `create_contact/$defs/Contact/properties/name` reads like one long path: the tool name and the JSON pointer are glued together. | Text output now shows `create_contact  /$defs/Contact/properties/name`. |
| 1.3 | `email: str \| None = None` was reported **lossy** ("omitted and null can no longer be distinguished"). But Pydantic sets `"default": null`, so for my server omitted **means** null and nothing is lost. A false alarm makes me distrust the tool. | T11b now recognises `default: null`. When a property's default is null, omitting it and sending null are equivalent, so the change is reported `reversible` (rule `optional-nullable-default-null`) and `denormalize_args` drops the null. Implemented in both languages, with new goldens. |
| 1.4 | Every target is checked by default. That's fine for a server builder, but I wanted to know what to put in CI. | The how-to has a ready-made GitHub Actions step and a pytest example. |
| 1.5 | To gate CI in pytest, I listed my tools with `server.list_tools()`, which gives MCP SDK `Tool` objects. `normalize_tools` wanted plain dicts. | `normalize_tools` now accepts MCP SDK `Tool` objects (any pydantic model) as well as dicts. |

Outcome: the open map was the only blocker. I changed `metadata: dict[str, str]` to `list[KeyValue]` and every
target passed. The remaining `lossy` entries are length and range constraints the model may ignore; my
handler already validates them. See `examples/server-builder/`.
