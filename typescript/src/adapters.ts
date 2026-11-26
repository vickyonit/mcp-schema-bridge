/** Provider request payloads (plain objects matching each official SDK's tool shape). */
import { loadRules } from "./core/rules.js";
import { type ToolsetResult } from "./core/toolset.js";

export type Api = "genai" | "openai-chat" | "openai-responses" | "anthropic-messages";
const PROVIDER: Record<Api, string> = { genai: "gemini", "openai-chat": "openai", "openai-responses": "openai", "anthropic-messages": "anthropic" };

export function toSdkPayload(result: ToolsetResult, api: Api): Record<string, unknown>[] {
  const provider = loadRules(result.target).provider;
  if (PROVIDER[api] !== provider) throw new Error(`api '${api}' does not match the provider of target '${result.target}' (${provider})`);
  const desc = (d: string | null) => (d === null ? {} : { description: d });
  switch (api) {
    case "genai": // @google/genai Tool
      return [{ functionDeclarations: result.tools.map((t) => ({ name: t.name, ...desc(t.description), parametersJsonSchema: t.schema })) }];
    case "openai-chat":
      return result.tools.map((t) => ({ type: "function", function: { name: t.name, ...desc(t.description), parameters: t.schema, strict: t.strict } }));
    case "openai-responses":
      return result.tools.map((t) => ({ type: "function", name: t.name, ...desc(t.description), parameters: t.schema, strict: t.strict }));
    case "anthropic-messages":
      return result.tools.map((t) => ({ name: t.name, ...desc(t.description), input_schema: t.schema, strict: t.strict }));
  }
}
