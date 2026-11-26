# For framework authors

## Where it fits

```
MCP tools/list ──► normalize_tools(tools, target) ──► provider request (to_sdk_payload)
                                                              │
MCP tools/call ◄── denormalize_args(tool, model_args) ◄── model tool call
```

## Recommendations

- **Normalize once per server toolset and target, and cache the result.** `ToolsetResult.to_dict()`
  and `NormalizedTool.from_dict()` round-trip. Each `NormalizedTool` carries a `fingerprint` covering
  the original tool, the library version, the rules version and the target. `denormalize_args` refuses
  a reverse map whose fingerprint or `rules_version` does not match (`ReverseMismatchError`), so a
  stale cache fails loudly instead of mistranslating.
- **Re-normalize** when the server sends `notifications/tools/list_changed`, or after upgrading
  `mcp-schema-bridge`.
- **Always call `denormalize_args`** before `tools/call`, even for targets that look like
  pass-through. It is cheap and correct when there is nothing to undo.
- **Show the report to users.** `lossy` entries mean the model may send values the server rejects. The
  server still validates; the report tells you why a call might fail. `fatal` tools are in
  `ToolsetResult.rejected`.
- **Strict modes:**
  - Pass `NormalizeOptions(strict_fallback=True)` to keep tools that cannot be strict, demoted to the
    non-strict sibling.
  - For `anthropic-strict`, pass `reserved_budget=Budget(...)` if your request also uses strict tools
    or an output schema of your own.
- **Thread safety:** all functions are pure, and rules are loaded once and cached read-only. They are
  safe to call concurrently.
- **Opt-in repairs:** `denormalize_args(..., repairs={"int_from_integral_float", "enum_case_insensitive"})`
  fixes two common model quirks. Repairs are applied only when unambiguous and always reported.

## Stability

- Before 1.0, a minor release can change normalized output (see [PLAN.md §10.1](PLAN.md)). Rules
  changes are listed under "Provider rule updates" in the changelog.
- `rules_version` is stamped into every report and reverse map.
