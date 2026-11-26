/** Provider request payloads (plain objects matching each official SDK's tool shape). */
import { loadRules } from "./core/rules.js";
import { type ToolsetResult } from "./core/toolset.js";

export type Api = "genai" | "openai-chat" | "openai-responses" | "anthropic-messages";
const PROVIDER: Record<Api, string> = { genai: "gemini", "openai-chat": "openai", "openai-responses": "openai", "anthropic-messages": "anthropic" };

type JsonSchema = Record<string, unknown>;
/** Structurally compatible with @google/genai `Tool`. */
export interface GenaiTool { functionDeclarations: { name: string; description?: string; parametersJsonSchema: JsonSchema }[] }
/** Structurally compatible with openai `ChatCompletionTool` (function). */
export interface OpenAIChatTool { type: "function"; function: { name: string; description?: string; parameters: JsonSchema; strict: boolean } }
/** Structurally compatible with openai `Responses.FunctionTool`. */
export interface OpenAIResponsesTool { type: "function"; name: string; description?: string; parameters: JsonSchema; strict: boolean }
/** Structurally compatible with @anthropic-ai/sdk `Tool`. */
export interface AnthropicTool { name: string; description?: string; input_schema: JsonSchema & { type: "object" }; strict: boolean }

export function toSdkPayload(result: ToolsetResult, api: "genai"): GenaiTool[];
export function toSdkPayload(result: ToolsetResult, api: "openai-chat"): OpenAIChatTool[];
export function toSdkPayload(result: ToolsetResult, api: "openai-responses"): OpenAIResponsesTool[];
export function toSdkPayload(result: ToolsetResult, api: "anthropic-messages"): AnthropicTool[];
export function toSdkPayload(result: ToolsetResult, api: Api): (GenaiTool | OpenAIChatTool | OpenAIResponsesTool | AnthropicTool)[];
export function toSdkPayload(result: ToolsetResult, api: Api): (GenaiTool | OpenAIChatTool | OpenAIResponsesTool | AnthropicTool)[] {
  const provider = loadRules(result.target).provider;
  if (PROVIDER[api] !== provider) throw new Error(`api '${api}' does not match the provider of target '${result.target}' (${provider})`);
  const desc = (d: string | null) => (d === null ? {} : { description: d });
  switch (api) {
    case "genai": // @google/genai Tool
      return [{ functionDeclarations: result.tools.map((t) => ({ name: t.name, ...desc(t.description), parametersJsonSchema: t.schema })) }];
    case "openai-chat":
      return result.tools.map((t) => ({ type: "function" as const, function: { name: t.name, ...desc(t.description), parameters: t.schema, strict: t.strict } }));
    case "openai-responses":
      return result.tools.map((t) => ({ type: "function" as const, name: t.name, ...desc(t.description), parameters: t.schema, strict: t.strict }));
    case "anthropic-messages":
      return result.tools.map((t) => ({ name: t.name, ...desc(t.description), input_schema: t.schema as JsonSchema & { type: "object" }, strict: t.strict }));
  }
}
