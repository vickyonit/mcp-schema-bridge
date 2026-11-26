/**
 * MCP client (TypeScript): connect to an MCP server, let an OpenAI model call its tools.
 *   OPENAI_API_KEY=... npx tsx agent.ts -- <server command>
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import OpenAI from "openai";
import { denormalizeArgs, normalizeTools, toSdkPayload } from "mcp-schema-bridge";

const argv = process.argv.slice(process.argv.indexOf("--") + 1);
const mcp = new Client({ name: "example-agent", version: "1.0.0" });
await mcp.connect(new StdioClientTransport({ command: argv[0]!, args: argv.slice(1) }));

const { tools: mcpTools } = await mcp.listTools();
const bridged = normalizeTools(mcpTools, "openai-strict", { strictFallback: true });
console.error(bridged.summary());

const openai = new OpenAI();
const response = await openai.responses.create({
  model: "gpt-4.1-mini",
  input: "Search for 'lamps', only 5 results, sorted by date.",
  tools: toSdkPayload(bridged, "openai-responses"), // typed: no cast needed
  tool_choice: "required",
});

for (const item of response.output) {
  if (item.type !== "function_call") continue;
  const tool = bridged.get(item.name);
  const args = tool ? denormalizeArgs(tool, JSON.parse(item.arguments)).args : JSON.parse(item.arguments);
  console.log(`model called ${item.name}(${item.arguments})\n  -> sent to MCP server: ${JSON.stringify(args)}`);
  const result = await mcp.callTool({ name: item.name, arguments: args as Record<string, unknown> });
  console.log("  <-", JSON.stringify(result.content));
}
await mcp.close();
