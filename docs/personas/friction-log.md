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

## Persona 2: MCP client / agent builder (Python, OpenAI Responses API)

Goal: "My agent connects to arbitrary MCP servers. OpenAI strict mode rejects some of their tools."

Steps: wrote `examples/client-builder/agent.py` (official `mcp` + `openai` SDKs, a `--raw` switch to
reproduce the problem) against a third-party Pydantic server. Run live with `gpt-4.1-mini`.

- `--raw`: `400 Invalid schema for function 'create_contact': 'additionalProperties' is required to be supplied and to be false`.
  Live verdicts show this for 157 of 164 corpus tools.
- With the bridge: the model calls `search({"query": "lamps", "limit": 5, "sort": "date"})`, the server
  receives valid arguments, and the tool with an open map is served non-strict through `strict_fallback`.

| # | What I felt | Change |
|---|---|---|
| 2.1 | I wrote my own loop to print the report and kept a `by_name` dict for `denormalize_args`. That's boilerplate in every client. | `ToolsetResult.get(name)` and `ToolsetResult.summary()` (the same text as the CLI) in both languages. |
| 2.2 | The summary said `4 tool(s) ok, 0 rejected … 1 fatal`, which looks contradictory. | The summary now says `(1 demoted to non-strict)`. The fatal entry explains why. |
| 2.3 | Recording live verdicts for OpenAI found two real bugs. A dropped tuple left `items: false`, meaning "no elements". Regex lookaround and backreferences make OpenAI strict fail with a 500. | Tuples are flattened to an items union. The OpenAI regex subset is now part of the rules, with evidence in `evidence/probes/openai-strict/`. |
| 2.4 | In TypeScript, `toSdkPayload` returned `Record<string, unknown>[]`, so passing it to `openai.responses.create` needed `as unknown as …`. | `toSdkPayload` has per-API overloads returning types structurally compatible with the official SDKs (`OpenAIResponsesTool`, `OpenAIChatTool`, `AnthropicTool`, `GenaiTool`). `examples/client-builder-ts/agent.ts` type-checks against the real `openai` types with no cast, and was run live. |

## Persona 3: MCP end user (gemini-cli, a third-party server)

Goal: "A server I installed breaks gemini-cli. I can change neither gemini-cli nor the server."

Steps: `examples/end-user/geo_server.py` emits a draft-07 tuple and a mixed-type enum. I ran the real
`gemini-cli` (headless) before and after putting the proxy in front of it.

- Before: the session failed for **every** prompt with `400 INVALID_ARGUMENT: schema at properties.from.items
  must be a boolean or an object`. One bad tool took down the whole conversation.
- After: `mcp-schema-bridge proxy --target gemini-json -- <original command>`. The model called the tool and
  answered "343.5 km".

| # | What I felt | Change |
|---|---|---|
| 3.1 | As an end user, the library API is useless to me. I can only edit my client's config. | New `mcp-schema-bridge proxy` command. You prefix the server command, and nothing else changes. |
| 3.2 | First attempt: "I do not have a distance tool". That was not a schema problem: headless gemini-cli hides tools that need confirmation. Very confusing to debug. | The how-to and the example call out `"trust": true` for headless runs, and that the interactive UI needs no change. |
| 3.3 | The proxy prints its summary to stderr, which gemini-cli doesn't show me. | Documented `--report FILE`. The example writes `bridge-report.json`. |
| 3.4 | Which `--target` do I pick for my app? | The how-to has a table mapping clients to targets. |
| 3.5 | Resources and prompts from the wrapped server disappear behind the proxy. | Documented limitation (tools only). Candidate for the next version. |
