# How to use mcp-schema-bridge

Pick the section that describes you. Every recipe here was run for real; the examples linked from
each section are in [`examples/`](../examples/).

| You are… | Your problem | What to use |
|---|---|---|
| [An MCP **server** builder](#1-mcp-server-builders-check-your-tools-before-you-ship) | "Will my tools work in Gemini, ChatGPT/OpenAI and Claude?" | `mcp-schema-bridge check` in CI |
| [An MCP **client** / agent builder](#2-mcp-client-and-agent-builders-normalize-in-your-tool-loop) | "Some servers' tools make the model API return 400, or get silently ignored." | `normalize_tools` + `denormalize_args` in your loop |
| [An MCP **user**](#3-mcp-users-fix-a-server-that-breaks-your-app-without-changing-anything) | "A server I installed breaks my app, and I can't change either." | `mcp-schema-bridge proxy` in your client config |

### Which target?

Pick the target that matches the model API your app sends tools to:

| Your app sends tools to… | `--target` |
|---|---|
| Gemini (gemini-cli, google-genai `parameters_json_schema`, Vertex/AI Studio function calling) | `gemini-json` |
| OpenAI with strict function tools (Structured Outputs, Agents SDK default, Responses API) | `openai-strict` |
| OpenAI with `strict: false` | `openai` |
| Claude with `strict: true` tools | `anthropic-strict` |
| Claude (normal tools) | `anthropic` |

Not sure? Run `mcp-schema-bridge check` without `--target`. It shows every target side by side.

---

## 1. MCP server builders: check your tools before you ship

Example: [`examples/server-builder/`](../examples/server-builder/) (a realistic Pydantic server).

```bash
pip install "mcp-schema-bridge[cli]"
mcp-schema-bridge check --stdio -- python my_server.py        # or: node build/index.js, uvx my-server, ...
```

You get one block per target. `fatal` means the tool is unusable on that API. Each `lossy` or `fatal`
line ends with a `fix:` line describing what to change in your server:

```
openai-strict: 1 tool(s) ok, 1 rejected; ...
  [fatal] create_contact  /$defs/Contact/properties/metadata additionalProperties: an object without
          declared properties (a map) cannot be expressed in strict mode (core/open-object-unsupported)
      fix: declare the keys as properties, or model a map as a list of {key, value} objects
           (Pydantic: list[KeyValue] instead of dict[str, str]) ...
```

The most common fixes:

| Report says | Change in your server |
|---|---|
| map / open object (`dict[str, X]`, `Record<string, X>`, `{type: object}`) | Declare properties, or use a list of `{key, value}` objects |
| `minLength` / `pattern` / `minimum` … "not enforced" | Keep them, but also validate in your handler. The model may ignore them |
| optional + nullable "ambiguous" | Give it `default: null` (Pydantic `= None`) if null means "not provided" |
| tool name invalid | Use only letters, digits, `_` and `-`, 64 characters or fewer |
| recursion only through required fields | Make the recursive field optional or nullable |

All rules and fixes: [rules.md](rules.md).

**Gate it in CI.** Either run the CLI, which exits 1 when any tool is rejected:

```yaml
# .github/workflows/mcp-schemas.yml
- run: pipx run --spec "mcp-schema-bridge[cli]" mcp-schema-bridge check --fail-on fatal --stdio -- python my_server.py
```

or write a test (MCP SDK `Tool` objects are accepted directly):

```python
import asyncio, pytest
from mcp_schema_bridge import TARGETS, normalize_tools
from my_server import server

@pytest.mark.parametrize("target", TARGETS)
def test_tools_work_everywhere(target):
    result = normalize_tools(asyncio.run(server.list_tools()), target)
    assert result.rejected == [], result.summary()
```

Use `--fail-on lossy` if you want to be told about every constraint a model might ignore.

---

## 2. MCP client and agent builders: normalize in your tool loop

Examples: [`examples/client-builder/agent.py`](../examples/client-builder/agent.py) (Python) and
[`examples/client-builder-ts/agent.ts`](../examples/client-builder-ts/agent.ts) (TypeScript). Both were
run live with OpenAI. Raw MCP schemas got `400 … 'additionalProperties' is required to be supplied and
to be false`; with the bridge, the call went through.

The loop is the same in every language:

```
tools/list ─► normalize_tools(tools, target) ─► to_sdk_payload(...) ─► model
tools/call ◄─ denormalize_args(tool, args)    ◄──────────────────────── function call
```

```python
from mcp_schema_bridge import NormalizeOptions, denormalize_args, normalize_tools, to_sdk_payload

bridged = normalize_tools((await mcp.list_tools()).tools, "openai-strict", NormalizeOptions(strict_fallback=True))
log.info(bridged.summary())                                  # what changed, per tool
response = openai.responses.create(model=..., input=..., tools=to_sdk_payload(bridged, "openai-responses"))

for call in (o for o in response.output if o.type == "function_call"):
    tool = bridged.get(call.name)
    args = denormalize_args(tool, json.loads(call.arguments)).args   # removes injected nulls, unwraps, ...
    result = await mcp.call_tool(call.name, args)
```

```ts
import { denormalizeArgs, normalizeTools, toSdkPayload } from "mcp-schema-bridge";

const bridged = normalizeTools((await mcp.listTools()).tools, "openai-strict", { strictFallback: true });
const response = await openai.responses.create({ model, input, tools: toSdkPayload(bridged, "openai-responses") });
for (const item of response.output) {
  if (item.type !== "function_call") continue;
  const args = denormalizeArgs(bridged.get(item.name)!, JSON.parse(item.arguments)).args;
  await mcp.callTool({ name: item.name, arguments: args as Record<string, unknown> });
}
```

Recommendations:

- **Always call `denormalize_args`.** Strict mode makes optional fields required and nullable, so the
  model sends `null` for "not provided". Many servers treat that differently from a missing key.
- **Use `strict_fallback=True`.** A tool that can't be made strict (for example one with a free-form map)
  is offered non-strict instead of disappearing.
- **Cache per server and target.** Results serialize (`to_dict()` / `NormalizedTool.from_dict`). Re-normalize on
  `notifications/tools/list_changed` or after upgrading. Python and TypeScript produce identical results.
- For Gemini use `to_sdk_payload(result, "genai")`. For Claude use `"anthropic-messages"`.

More in [framework-authors.md](framework-authors.md).

---

## 3. MCP users: fix a server that breaks your app, without changing anything

Example: [`examples/end-user/`](../examples/end-user/). It was verified with the real gemini-cli, which
failed every request with `400 INVALID_ARGUMENT: schema at properties.from.items must be a boolean or an object`
until the server was put behind the proxy.

The proxy is an MCP server that starts the real server, serves its tools with fixed schemas, and maps
arguments back. In your client's MCP config, **put the proxy in front of the original command**:

```jsonc
// before
"geo": { "command": "npx", "args": ["-y", "some-mcp-server"] }

// after
"geo": {
  "command": "uvx",
  "args": ["--from", "mcp-schema-bridge[cli]", "mcp-schema-bridge", "proxy", "--target", "gemini-json",
           "--", "npx", "-y", "some-mcp-server"]
}
```

This works the same in gemini-cli (`.gemini/settings.json`), Claude Desktop (`claude_desktop_config.json`),
Cursor, VS Code, and any other client that launches MCP servers as a command.

Useful flags:

| Flag | What it does |
|---|---|
| `--report bridge-report.json` | Writes everything the proxy changed. Clients usually hide the proxy's stderr |
| `--strict-fallback` | For strict targets, serve unfixable tools non-strict instead of hiding them |
| `--no-hints` | Don't append dropped constraints to tool descriptions |

Troubleshooting:

- **"I don't have that tool"** in headless gemini-cli (`gemini -p …`): headless mode only offers tools it can
  run without asking. Set `"trust": true` on that server, or use the interactive UI.
- **A tool disappeared behind the proxy:** it cannot be expressed for your target. Run with `--report` and
  look at `rejected`, or add `--strict-fallback`.
- **Resources or prompts missing:** the proxy forwards tools only (for now).
