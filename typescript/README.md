# mcp-schema-bridge (TypeScript)

Normalize MCP tool schemas for **Gemini**, **OpenAI** and **Anthropic**. You get a lossiness report of
every change, and `denormalizeArgs` maps the model's arguments back to what the MCP server expects.

The TypeScript package produces output **byte-identical** to the Python package on the shared corpus.
That includes report messages, key order and fingerprints, so cached tools are interchangeable between
the two. The full documentation is in the [main README](https://github.com/vickyonit/mcp-schema-bridge#readme).

```bash
npm install mcp-schema-bridge   # Node >= 22, zero dependencies, ESM + CJS + types
```

```ts
import { denormalizeArgs, normalizeTools, toSdkPayload } from "mcp-schema-bridge";

const result = normalizeTools(mcpTools, "openai-strict", { strictFallback: true });
for (const e of result.report.entries) if (e.severity === "lossy") console.warn(e.tool, e.message);

const tools = toSdkPayload(result, "openai-responses"); // strict is always set explicitly
// ... call the model, then for each function call:
const tool = result.tools.find((t) => t.name === call.name)!;
const args = denormalizeArgs(tool, JSON.parse(call.arguments)).args; // injected nulls removed
await mcp.callTool({ name: call.name, arguments: args });
```

Targets: `gemini-json`, `openai`, `openai-strict`, `anthropic`, `anthropic-strict`.

## Differences from the Python API

- camelCase names: `normalizeTools`, `normalizeSchema`, `denormalizeArgs`, `toSdkPayload`, and
  options such as `strictFallback`, `maxRefDepth` and `maxDescriptionChars`.
- `NormalizedTool.schema` is a plain object. `schemaOrdered` keeps exact key order, including
  integer-like property names, which plain JavaScript objects reorder.
- Numbers are IEEE doubles, so there is no `big_int` option. Integers beyond ±(2^53−1) are rejected.
  The `int_from_integral_float` repair has no effect, because `5.0` and `5` are the same number in
  JavaScript.
- `toSdkPayload(result, "genai")` returns plain `@google/genai` `Tool` objects
  (`functionDeclarations[].parametersJsonSchema`). No SDK is imported.

License: Apache-2.0.
