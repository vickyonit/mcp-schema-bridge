# Examples

End-to-end loops: MCP `tools/list` → `normalize_tools` → model API → `denormalize_args` → MCP `call_tool`.

| Example | Target | Verified |
|---|---|---|
| [`gemini_loop.py`](gemini_loop.py) | `gemini-json` | Run live against `@modelcontextprotocol/server-everything` |
| [`openai_loop.py`](openai_loop.py) | `openai-strict` (+ `strict_fallback`) | Type-checked against the OpenAI SDK; not yet run live (no key in CI) |
| [`anthropic_loop.py`](anthropic_loop.py) | `anthropic-strict` (+ `strict_fallback`) | Type-checked against the Anthropic SDK; not yet run live (no key in CI) |

```bash
cd examples
GEMINI_API_KEY=... uv run --with-editable ../python[sdks,cli] gemini_loop.py -- npx -y @modelcontextprotocol/server-everything
```

Note: `google-genai` prefers `GOOGLE_API_KEY` over `GEMINI_API_KEY` when both are set.
