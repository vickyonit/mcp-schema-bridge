# ADR-0001: Build `mcp-schema-bridge` rather than contribute to an existing project

- Status: Accepted (provisional; revisit after maintainer outreach)
- Date: 2026-11-26

## Context

Several projects already convert JSON Schema / MCP `inputSchema` into provider tool formats. Registry metadata checked on 2026-11-26:

| Project | Registry version (2026-11-26) | Self-description |
|---|---|---|
| `tool-schema` (npm) | 0.4.2 | "Convert any JSON Schema into a valid tool / function calling schema for OpenAI, Anthropic, Gemini and MCP. Zero dependencies." |
| `mcpschema` (PyPI) | 0.1.0 | "Convert MCP tool schemas to OpenAI, Anthropic, Gemini, and other LLM provider formats — zero dependencies" |
| `mcp-schema-normalize` (PyPI) | 0.1.1 | Targets llama.cpp's grammar subset (local backends) |
| `@mastra/schema-compat` (npm) | 1.4.1 | "Tool schema compatibility layer for Mastra.ai" |
| `pydantic-ai-slim` (PyPI) | 2.75.0 | Contains JSON Schema transformers for Gemini / OpenAI strict (framework-internal) |

Provider SDKs also ship single-provider helpers (Anthropic `transform_schema()`, OpenAI `to_strict_json_schema`).

None of the self-descriptions above claim the three properties this project is built around:

1. An **argument round-trip** (`denormalize_args`) back to the original MCP schema.
2. A **machine-readable lossiness report** with a published schema and a property-tested "no silent loss" guarantee.
3. **Evidence-backed provider rules** (recorded API verdicts / probes, dated), re-verified nightly.

Those claims are about *self-descriptions*; we have not audited each project's source. Before any public comparison is published, each row will be re-checked against a pinned version and phrased neutrally.

## Decision

Build `mcp-schema-bridge` as a standalone, framework-agnostic library (Python first, TypeScript second).

## Consequences

- Outreach to the closest projects (`@mastra/schema-compat`, Pydantic AI) is a maintainer action, tracked in the launch checklist; if a maintainer prefers upstreaming, this ADR is revisited.
- The README's "Why not X?" section must be backed by the re-check above.
