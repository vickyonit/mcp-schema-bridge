# Implementation Plan: `mcp-schema-bridge`

> **Your MCP tools work on Claude but 400 on Gemini, or they quietly lose constraints under OpenAI strict mode.**
> `mcp-schema-bridge` rewrites MCP tool schemas for each model API. It reports exactly what it changed, and it maps the model's arguments back so they satisfy the original MCP server.

| | |
|---|---|
| Repo | `~/workspace/mcp-schema-bridge` (public on GitHub) |
| Packages | PyPI `mcp-schema-bridge` (import `mcp_schema_bridge`) and npm `mcp-schema-bridge`. Both names were free on 2026-11-26 |
| Status | Plan, revision 4 (merged v1+v2, then four independent review passes) |
| Provider facts | From official docs, 2026-11-26. **All provisional until Phase 0 records evidence** (§4) |
| Process | Strict TDD, one logical change per commit (§9.1) |

---

## 0. Decisions for the author (confirm before Phase 0)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | License | **Apache-2.0** | Includes a patent grant, which frameworks that vendor the code will want. MIT is also fine. Whichever you pick, record it in ADR-0002 before the first push |
| D2 | v0.1 scope | **Python only.** TypeScript ships in v0.2 with byte-identical output | Halves the time to a credible first release. The README must not claim TS parity until it ships |
| D3 | Legacy Gemini `parameters` target (OpenAPI `Schema`) | **Defer to v0.2**, unless Phase 0 shows `google-genai`/ADK/gemini-cli still send it by default | `parametersJsonSchema` is the modern surface and loses less |
| D4 | Contribution policy | **DCO** (GitHub App), not a CLA | Lightweight. Standard for solo maintainers |
| D5 | Build vs contribute | Decided in Phase 0 (ADR-0001) | Prior art exists (§2). We build only if the differentiators hold up |

---

## 1. Problem

MCP servers publish tools as JSON Schema `inputSchema`. The MCP spec requires `type: "object"` at the root and uses 2020-12 as the default dialect. Each model API accepts a different, changing subset of JSON Schema:

- Some schemas are **rejected** (400 / `INVALID_ARGUMENT`).
- Some keywords are **silently stripped**.
- Strict modes **restructure** the schema (optional fields become required+nullable, objects are closed), so the model's output differs from what the MCP server expects.

Frameworks each patch this differently. Their patches are incomplete, report nothing, and don't translate arguments back.

## 2. Prior art and positioning

The Phase 0 review takes about a day. Each row gets a link, the version checked, and a date, and is phrased neutrally ("as of vX.Y"). **The rows below are leads to verify, not claims.**

| Project | What it does (to verify) |
|---|---|
| `tool-schema` (npm) | JSON Schema → OpenAI / OpenAI-strict / Anthropic / Gemini / MCP shapes |
| `mcpschema` (PyPI) | MCP `inputSchema` → tool shapes for 6 providers |
| `mcp-schema-normalize` (PyPI) | llama.cpp grammar subset, plus a LiteLLM hook |
| Mastra `@mastra/schema-compat` | Per-provider schema compatibility layers |
| Pydantic AI `JsonSchemaTransformer` | Gemini and OpenAI-strict transformers |
| OpenAI Agents SDK `ensure_strict_json_schema`; OpenAI SDK `to_strict_json_schema` | OpenAI strict |
| Anthropic SDK `transform_schema()` | Anthropic strict. Moves dropped constraints into descriptions |
| Vercel AI SDK, LiteLLM, `google-genai`, gemini-cli, FastMCP, LangChain | Conversions built into each framework |

**Differentiators.** The README claims only those true in the release being announced:

1. **Round-trip.** `denormalize_args()` turns model output into arguments that satisfy the *original* MCP schema, except where the report explicitly says otherwise.
2. **A trustworthy report.** It is machine-readable, has a published JSON Schema and stable rule ids, and a property test guarantees no keyword is changed without an entry (§8.3). CI can fail on `lossy`.
3. **Evidence-backed rules.** Every rule records its evidence type (`recorded` / `probe` / `doc`), source URL and date verified. A nightly job re-checks recorded verdicts.
4. *(v0.2)* Python and TypeScript produce byte-identical output on a shared corpus.

Before deciding, we reach out to the maintainers of the closest project (likely Mastra or Pydantic AI). ADR-0001 then records "we talked to X; here's why separate", or we contribute to their project instead. **A reply is not required to finish Phase 0.**

---

## 3. Scope

**v0.1 (Python)**
- `normalize_schema`, `normalize_tools` and `denormalize_args`.
- The lossiness report.
- Tool-name and property-key **validation** (no rewriting).
- Targets: `gemini-json`, `openai`, `openai-strict`, `anthropic`, `anthropic-strict`.
- SDK payload adapters for `google-genai`, `openai` (Chat Completions + Responses) and `anthropic`.
- CLI commands `check` and `normalize`.

**v0.2**
- TypeScript port with byte-identical output.
- Legacy `gemini` target (D3), together with T6 enum stringification and the `uncoerce_enum` reverse op.
- Tool-name **rewriting** with a reverse name map.
- Opt-in omit sentinel (T11c).
- `map_as_entries` (T10b).
- `diff` and `report` CLI commands.
- Rules-snapshot pinning.

**Not planned**
- Runtime checks (OAuth, reachability).
- `outputSchema` normalization.
- MCP resources and prompts.
- Fetching remote `$ref`. The MCP spec forbids network dereferencing.

**"What we can't fix" (in the README from day one)**
- `oneOf` exclusivity, on targets that only support `anyOf`.
- Under `openai-strict`, telling "omitted" apart from "explicit null" for fields that are both optional and nullable (until the v0.2 sentinel).
- Open maps (`additionalProperties: {schema}`) under strict targets.
- Required recursion on `anthropic-strict`.
- `$dynamicRef` and `$recursiveRef`.
- Tool names the target forbids. For example, MCP allows `.` in names but Anthropic does not. v0.1 rejects these and v0.2 will rewrite them.

---

## 4. Targets: what we know, and what still needs evidence

Each cell becomes a row in `rules/<target>.json` with these fields: `id`, `evidence: recorded|probe|doc`, `source_url`, `verified_on`, `models`. The README compatibility matrix is **generated** from these rows. Provider numbers are never hand-typed into the README.

**Strict targets** = `openai-strict` and `anthropic-strict`. These are the only targets with `strict: true`. All others are non-strict.

### `gemini-json`: `FunctionDeclaration.parametersJsonSchema`

**Doc (FunctionDeclaration reference)**
- The root must describe an object.
- Mutually exclusive with `parameters`.
- Function names allow `a-zA-Z0-9_.:-`, up to 128 characters.

**Inferred from the `responseJsonSchema` docs; Phase 0 must re-check each for `parametersJsonSchema`**
- Supported:
  - Types including `null`, and type arrays.
  - `anyOf`.
  - `$ref` and `$defs`. Recursion is allowed only if the recursive field is optional.
  - `additionalProperties` as a boolean or a schema.
  - `prefixItems`, `minItems`/`maxItems`, `minimum`/`maximum`, `enum`.
  - `format`: date-time, date, time.
- Silently **stripped**: `minLength`/`maxLength`, `minProperties`/`maxProperties`, `uniqueItems`, `contains`.
- Overly complex schemas fail with `400 INVALID_ARGUMENT`.

**Open (Phase 0)**
- Whether `pattern`, `const`, `oneOf`, `not`, `if/then/else`, `dependent*`, `exclusiveMinimum` and `multipleOf` are rejected or stripped.
- Whether a required recursive field is rejected.
- Whether `functionCall.args` returns integers as floats.
- How Vertex AI differs from AI Studio.

### `openai` (non-strict) and `openai-strict`: function tools

**Doc (strict)**
- The root must be an object, and not `anyOf`.
- Every object needs `additionalProperties: false`, and every property must be listed in `required`.
- Optional fields are expressed as `type: [T, "null"]`.
- `$defs`, `$ref` and recursion (including `"#"`) are supported.
- Supported keywords:
  - String: `pattern`, `format` (date-time, time, date, duration, email, hostname, ipv4, ipv6, uuid; **no `uri`**).
  - Number: `multipleOf`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`.
  - Array: `minItems`, `maxItems`.
- Unsupported: `allOf`, `not`, `if/then/else`, `dependentRequired`, `dependentSchemas`. `minLength`/`maxLength`, `patternProperties` and `uniqueItems` are not listed, so treat them as unsupported until Phase 0.
- Limits **per schema**:
  - 5,000 properties.
  - 10 levels of nesting.
  - 120,000 characters across property names, definition names, enum values and const values.
  - 1,000 enum values.
  - 15,000 characters for any single string enum with more than 250 values.
- Fine-tuned models support fewer constraints, so rules can be model-dependent.

**Doc (Responses API).** If `strict` is not set, the API *attempts to make the schema strict itself*. Our adapters therefore always set `strict` explicitly (§7.4).

**Open (Phase 0)**
- `oneOf`.
- `$ref` with sibling keywords.
- The regex dialect for `pattern`.
- Arrays without `items`.
- The function-name regex and length (the docs say nothing).
- Whether any limits apply per request.

### `anthropic` (non-strict) and `anthropic-strict`

**Doc.** Tool names must match `^[a-zA-Z0-9_-]{1,128}$`.

**Doc (strict): supported**
- Types: object, array, string, integer, number, boolean, null.
- `enum`/`const` with primitive values only.
- `anyOf`, and `allOf` with restrictions.
- Internal `$ref`, `$defs` and `definitions`.
- `default` and `required`.
- `pattern`, but **without** backreferences, lookaround, `\b`/`\B`, or large `{n,m}`.
- `format`: date-time, time, date, duration, email, hostname, uri, ipv4, ipv6, uuid.
- `minItems` of 0 or 1.
- `additionalProperties` must be `false`.

**Doc (strict): unsupported**
- Recursion, `oneOf`, `not`, external `$ref`.
- `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, `maxItems`, and any other array constraint.
- `anyOf` alongside `type`/`properties`.
- `allOf` with conflicting branches, or with two or more branches when one directly contains `$ref`/`anyOf`/`allOf`.

**Doc (strict): limits per request**, counted across all strict tools plus any `output_config.format` schema:
- 20 strict tools.
- 24 optional parameters.
- 16 parameters with union types (`anyOf` or a type array).
- An undocumented compiled-grammar limit ("Schema is too complex for compilation").

Strict mode also doesn't guarantee the case of enum values.

**Open (Phase 0)**
- Property-key restrictions (`^[a-zA-Z0-9_.-]{1,64}$` has been reported).
- How the optional and union counts are computed across nesting.

### MCP input (spec 2026-07-28)

**Doc**
- `inputSchema` is `{type: "object", ...}`.
- The default dialect is 2020-12, and implementations MUST error on unsupported dialects.
- Implementations MUST NOT dereference network `$ref`.
- Tool names SHOULD match `[A-Za-z0-9_.-]{1,128}`.
- `x-mcp-header` and other `x-*` keys exist.

---

## 5. Design principles

1. **No silent change of meaning.** Every change becomes a report entry, and the provenance property enforces this (§8.3 #4).
2. **Rules are data.** Provider facts are never hard-coded. Rule files are copied into each package by a build script, the copies are committed, and CI diffs them against the source (§10.2).
3. **Pure and deterministic.** No I/O and no input mutation. Output is stable across runs, platforms and (in v0.2) languages (§6.6).
4. **Idempotent.** For one target, `normalize_schema(normalize_schema(x).schema)` gives the same schema and no new report entries. This covers `normalize_schema` and per-tool schemas only. It does not cover whole toolsets, where fallback can change a tool's target.
5. **Zero runtime dependencies in the core.** SDKs and the MCP client are optional extras.
6. **Fail loudly.** If no safe rewrite keeps a tool usable, it is rejected with a `fatal` entry. It is never quietly left unusable.
7. **Property order is preserved.** Providers generate fields in schema order, so `properties` and `required` keep their source order.

---

## 6. Specification

These files are written as `spec/*` in Phase 1, before any normalizer code, and frozen at v0.1.

### 6.1 Public API (Python; the TS API in v0.2 mirrors it in camelCase)

```python
Target = Literal["gemini-json", "openai", "openai-strict", "anthropic", "anthropic-strict"]

@dataclass(frozen=True)
class Budget:                                  # anthropic-strict per-request usage outside our tools
    strict_tools: int = 0
    optional_params: int = 0
    union_params: int = 0

@dataclass(frozen=True)
class NormalizeOptions:
    hints: bool = True                         # append dropped validation constraints to descriptions (§6.5)
    on_unsupported: Literal["report", "raise"] = "report"   # "raise": the first fatal entry raises UnsupportedSchemaError
    max_ref_depth: int = 3                     # recursion unrolling on targets that forbid recursion (T2a)
    max_nodes: int = 10_000                    # input AND output node cap; exceeding → LimitExceededError
    max_depth: int = 64                        # input nesting cap; exceeding → LimitExceededError
    max_description_chars: int | None = None   # truncates ORIGINAL text (ellipsis counted within limit), never the hint
    strict_fallback: bool = False              # demote unfixable/over-budget tools to the non-strict sibling target (T17)
    reserved_budget: Budget | None = None
    big_int: Literal["reject", "round"] = "reject"   # |n| > 2**53-1; "round" emits a coerced/lossy entry

normalize_schema(schema: dict, target: Target, opts=None) -> NormalizeResult
normalize_tools(tools: list[dict], target: Target, opts=None) -> ToolsetResult
denormalize_args(tool: NormalizedTool | NormalizeResult, args: dict, *, strict: bool = False,
                 repairs: frozenset[Repair] = frozenset()) -> DenormalizeResult
to_sdk_payload(result: ToolsetResult, api: Literal["genai", "openai-chat", "openai-responses", "anthropic-messages"]) -> list
```

**Data types.** Each is published as JSON Schema under `spec/`.

- `NormalizeResult = {target, strict, schema: dict | None, report, reverse, fingerprint}`.
  - `schema` is `None` when the result is `fatal` and `on_unsupported="report"`.
  - With `strict_fallback`, a fatal result on a strict target is re-normalized for its non-strict sibling target. `target` and `strict` then reflect that sibling, and the report includes a `fallback` entry.
- `NormalizedTool = {name, description, target, strict, schema, reverse, fingerprint}`.
- `ToolsetResult = {target, tools: [NormalizedTool], rejected: [Rejection], report}`.
- `Rejection = {name, target, reasons: [ReportEntry]}`.
- `DenormalizeResult = {args, warnings: [ReportEntry]}`.
- `Repair` is one of `"int_from_integral_float"` or `"enum_case_insensitive"`. Repairs are opt-in, applied only when unambiguous, and always reported.
- **Fingerprint.** It is the sha256 of the JCS encoding of `{original input, library_version, rules_version, target}`. `reverse` embeds the same value. `denormalize_args` raises `ReverseMismatchError` in either case:
  - `reverse.fingerprint` differs from the tool's `fingerprint`;
  - `reverse.rules_version` differs from the loaded rules.
  
  This stops a stale cache from silently mistranslating arguments.
- **Errors.** All errors derive from `SchemaBridgeError` and carry a JSON Pointer. The subclasses are:
  - `InvalidInputError`: bad JSON, duplicate keys, an unknown dialect, NaN or Infinity, lone surrogates, or a big int under `reject`.
  - `UnsupportedSchemaError`: only under `on_unsupported="raise"`.
  - `LimitExceededError`: `max_nodes` or `max_depth` exceeded.
  - `ReverseMismatchError`.

**`denormalize_args` behaviour**
- It is total by default. Unrecognized shapes (a missing wrapper, unknown keys, an unmapped value) pass through unchanged with a warning. With `strict=True` they raise instead.
- It walks the instance and the normalized schema together and follows `$ref`, so recursion and arrays work.
- It never evaluates `pattern` or `format`.

### 6.2 Report

```json
{
  "library_version": "0.1.0", "rules_version": "2026.11.26", "target": "openai-strict",
  "entries": [{
    "rule": "openai-strict/optional-to-nullable", "tid": "T11a",
    "tool": "create_contact",
    "source_path": "/properties/age", "target_path": "/properties/age", "instance_path": "/age",
    "keyword": "required", "action": "rewritten", "severity": "reversible",
    "original": null, "hinted": false
  }]
}
```

**`action`** is one of: `dropped | rewritten | inlined | merged | coerced | wrapped | narrowed | truncated | fallback | rejected`.

**`severity`** is one of:
- `info`: no behavioural change.
- `reversible`: the model contract changed, and `denormalize_args` restores it exactly.
- `lossy`: a constraint or distinction is no longer enforced.
- `fatal`: the tool or schema was rejected.

The recommended CI threshold is `--fail-on lossy`.

**Fields**
- `rule` is a stable id of the form `<target or "core">/<slug>`. Each rule has a docs page at `docs/rules/<rule>.md`, and error messages link to it.
- `tid` names the transformation family (§6.4).
- Paths are RFC 6901 pointers. Escape `~`→`~0` first, then `/`→`~1`.
- `tool` is `null` when the entry comes from `normalize_schema`.
- `instance_path` is `null` when the anchor can be reached from more than one place (for example, a shared `$def`).

**Ordering.** Sort entries by `(tool ?? "", source_path, rule, keyword ?? "", target_path, action)`. Compare strings by UTF-16 code units (the same order JCS uses). The resulting order is total.

### 6.3 ReverseMap

The ReverseMap is a list of ops. Each op is anchored to a location in the **normalized** schema, which may be a pointer through `$defs`. The reverse walk follows `$ref`, so one anchor applies at every instance location that reaches it.

| op | Undo |
|---|---|
| `unwrap_root` | `{value: X}` → X |
| `drop_injected_null` | Value is `null` at an anchor where T11a injected nullability → remove the key |
| `uncoerce_enum` *(v0.2)* | String → original JSON value via a stored table, never re-parsed |
| `entries_to_object` *(v0.2)* | `[{key, value}]` → object. Duplicate keys raise an error |

**Branch matching.** If an anchor sits inside an `anyOf` whose branches can't be told apart, normalization emits a `lossy` entry with rule `core/reverse-ambiguous-branch`. The reverse then applies the first branch that **structurally matches**. A branch matches when all three hold:
- The instance's primitive JSON type is allowed by the branch's `type`.
- Every key in the branch's `required` is present.
- Every `const` or single-value `enum` in the branch is equal to the instance value.

`pattern`, `format` and bounds are never checked. Branches count as distinguishable when no instance can structurally match two of them.

### 6.4 Transformations and pipeline

**Transformation families** (`tid`s are stable; every report entry carries one):

| tid | What | Targets | Severity | Reverse |
|---|---|---|---|---|
| T1 | Strip annotation-only keywords: `$comment`, `examples`, `readOnly`, `writeOnly`, `deprecated`, `x-*` (incl. `x-mcp-header`), OpenAPI `discriminator`, plus `title`/`$id` where unsupported | all, per rules | info | – |
| T2a | Inline recursive `$ref` up to `max_ref_depth` | `anthropic-strict` | lossy (`truncated`) | – |
| T2b | Inline `$ref` that has siblings | where Phase 0 shows siblings are rejected | info | – |
| T2c | External or unresolved `$ref` | all | fatal | – |
| T3 | `$ref` siblings, draft-07: dropped | all | info | – |
| T4 | Split a multi-type array **without `null`** into `anyOf` (type-specific keywords go to their own branch; `[integer, number]` → `number`). **Never** splits `[T, "null"]` | targets that forbid multi-type arrays (rules flag) | info | – |
| T5 | `enum`/`const` with no `type`: infer it. `null` does not count as a separate type (`[c, null]` → `type: [T, "null"]`); other mixed types → `anyOf`, one per type | strict targets | info | – |
| T6 *(v0.2)* | Stringify non-string enums | `gemini` | reversible | `uncoerce_enum` |
| T7 | Merge `allOf` (§6.4.1) | `openai-strict`, `anthropic-strict`; others where the rules forbid it | info / lossy / fatal per rule | – |
| T8 | `oneOf` → `anyOf` | where `oneOf` is unsupported | lossy | – |
| T9 | Distribute keywords that sit beside an `anyOf` into each branch | `anthropic-strict`; others per rules | info | – |
| T10 | Close objects (§6.4.2) | strict targets | info / lossy / fatal | – |
| T11a/b | Optional → required + nullable (§6.4.3) | `openai-strict` | reversible / lossy | `drop_injected_null` |
| T12 | Drop unsupported validation keywords (classed in `spec/keyword-classes.json`), with a hint | per rules | lossy | – |
| T13 | `default`: keep where accepted, otherwise drop and hint | per rules | info | – |
| T14 | Root: a root that is not an object, or a root union (`anyOf`/`oneOf` at root, or object + `anyOf` where the target forbids it) → `{type: object, properties: {value: …}, required: ["value"]}` | per rules flag `root_union_allowed` | reversible | `unwrap_root` |
| T15 | `format` not on the allow-list: drop and hint | per rules | lossy | – |
| T16 | `pattern` that uses forbidden regex features (§6.4.4): drop and hint | per rules | lossy | – |
| T17 | Per-request budgets (§6.4.5) | `anthropic-strict` (+ OpenAI if Phase 0 finds any) | fatal / fallback | – |
| T18 | Validate tool name, property keys, and arrays without `items` | all, per rules | fatal | – |

**Pipeline.** Stages run in this order. Each stage is a pure function with its own unit tests.

| Stage | Runs | Notes |
|---|---|---|
| **S0 Parse** | Strict JSON, dialect detection, guards | Rejects duplicate keys, NaN/Infinity and lone surrogates. Big ints are handled by the `big_int` option. Enforces `max_nodes`/`max_depth`. Supported `$schema` values: 2020-12 (default), draft-07, and 2019-09 without `$recursiveRef`. Anything else raises `InvalidInputError` |
| **S1 Resolve** | Builds a ref index over the immutable original | Covers local pointers, `$id` base URIs and `$anchor`. Fragments are decoded percent-encoding first, then `~1`, then `~0`. External refs → T2c. `$dynamicRef` and `$recursiveRef` → fatal |
| **S2 Canonicalize** | Converts to one dialect-independent internal form | draft-07 tuple `items[]` + `additionalItems` → `prefixItems`/`items`. `dependencies` → `dependentRequired`/`dependentSchemas`. Boolean subschemas are normalized. OpenAPI `nullable: true` → type array. `$ref` siblings: draft-07 drops them (T3); 2020-12 turns **validation** siblings into `allOf: [{$ref}, {siblings}]`; **annotation-only** siblings (`description`, `title`, `default`) stay next to `$ref` |
| **S3 Merge** | T7 | `$ref` branches are resolved through the S1 index before merging |
| **S4 Inline** | T2a, T2b | Every other `$ref` is kept. Later stages also rewrite inside `$defs` |
| **S5 Root** | T14 | `"#"` self-refs become `$defs/__root` first (suffixed `_1`, `_2`, … on collision). All local `$ref`s are then rewritten to the new paths |
| **S6 Unions** | T8 → T9 → T5 → T4 | |
| **S7 Objects** | T10 | |
| **S8 Optional** | T11 | |
| **S9 Filter** | T1, T12, T13, T15, T16 | |
| **S10 Hints** | §6.5 | Runs after merging, so hints describe the merged constraints |
| **S11 Validate** | Per-schema limits; T18 | Measured on the final output |
| **S12 Finalize** | Prune unused `$defs` (info). The output never contains `$schema`, because output is always 2020-12 semantics | Runs last, so idempotence holds |
| **S13 Toolset** | T17 | `normalize_tools` only |

The walker understands the schema grammar by **position**. `properties`, `patternProperties`, `$defs`, `dependentSchemas` and `dependentRequired` hold *maps of names*, so a property called `title`, `$ref`, `type`, `a/b`, `a~b` or `__proto__` is never mistaken for a keyword. Each of these names has a corpus case.

#### 6.4.1 T7: `allOf` merge (`spec/allof-merge.md`)

- **`properties`**: the union across branches. A property that appears in several branches is merged recursively.
- **`required`**: the union, in the order keys are first seen.
- **`additionalProperties: false`** in a branch limits the merged properties to that branch's own properties. If another branch requires a property that this branch forbids, the schema is unsatisfiable and the merge is `fatal`.
- **Bounds and values**:
  - Numeric bounds: take the largest minimum and the smallest maximum.
  - `type`: the intersection, where `integer ∩ number = integer`.
  - `enum` and `const`: the intersection.
  - An empty result for any of these is `fatal`.
- **Repeated or conflicting validation keywords**: when `pattern` or `multipleOf` appears twice, or two `format` values conflict, keep the first and drop the rest. The dropped values become a hint (`lossy`).
- **`anyOf`/`oneOf` inside `allOf`**: distribute them as a cross-product, capped by `max_nodes`.
- **`not`, `if/then/else`, `unevaluated*`**: dropped (`lossy`).
- **Annotations**:
  - `description`: the branches' values are joined with `"\n\n"` in branch order.
  - `default`: the first one wins. A conflicting default gets an `info` entry.
  - `title`: the first one wins.

Every rule above has its own synthetic corpus case.

#### 6.4.2 T10: closing objects on strict targets

- An object that declares `properties` and has no `additionalProperties` gets `additionalProperties: false` (`narrowed`, `info`).
- An object with `additionalProperties` explicitly `true` or a schema, but which also declares `properties`, is closed too (`lossy`).
- An object with `additionalProperties: false` already set is left alone and produces no entry. This keeps the transform idempotent.
- An **open object with no declared properties** cannot be expressed on a strict target. This covers `{type: object}` on its own, and objects that rely on `additionalProperties: true/{…}`, `patternProperties` or `propertyNames`. Such an object is `fatal`, or triggers a fallback if `strict_fallback` is set. In v0.2, `map_as_entries` can rewrite it instead.
- A property whose schema is `{}` or `true` ("any value") is handled the same way.

#### 6.4.3 T11: optional → required + nullable (`openai-strict`)

**Definition: originally nullable.** A property is originally nullable if its *resolved* schema accepts `null`, meaning any of:
- `type` includes `"null"`;
- `enum` or `const` contains `null`;
- some `anyOf` branch accepts `null`;
- the schema is `{}` or `true`.

**Where nullability is injected.** At the use site. Nullability is **never added to the root of a `$def`**. An optional property declared *inside* a `$def`'s object body is a use site, so it is rewritten there.

**Injection rules by schema shape**
- `type: T` → `type: [T, "null"]`.
- `enum` gets `null` appended.
- `const: c` → `type: [typeof c, "null"], enum: [c, null]`.
- `{$ref}` → `anyOf: [{$ref}, {type: "null"}]`. Annotations such as the description or a hint go on this wrapper, not next to the `$ref`.
- An existing `anyOf` gets a `{type: "null"}` branch, unless one already accepts `null`.

**The two outcomes**
- **T11a.** The property was not originally nullable. It is `reversible`: the reverse op `drop_injected_null` removes a `null` value.
- **T11b.** The property was already nullable. It is `lossy`, with rule `openai-strict/optional-nullable-ambiguous`. A `null` value is passed through unchanged, so "omitted" and "explicit null" become indistinguishable. The omit sentinel (T11c) fixes this in v0.2.

**Defaults and anyOf branches**
- A `default` on an optional property is dropped and hinted. The server applies it when the key is absent.
- A property that is required within an `anyOf` branch stays non-nullable in that branch.

**Idempotence.** A property that is already required is never touched, so normalizing T11's output again changes nothing.

A corpus case covers a single `$def` used once as optional and once as required.

#### 6.4.4 Regex feature scanner (T16)

A small, purely syntactic scanner over ECMA-262 pattern syntax. It flags:
- backreferences;
- lookaround;
- `\b` and `\B`;
- `{n,m}` ranges above a threshold;
- Unicode property escapes;
- inline flags.

Each rules table lists the features its target forbids. The scanner never uses the host regex engine. Its test vectors live in `spec/regex-vectors.json` and are shared with the TS port.

#### 6.4.5 T17: per-request budgets

- **Counting rules.** How optional and union parameters are counted across nesting is defined as data in `rules/anthropic-strict.json`.
- **When counting happens.** After all rewrites (including inlining), with `reserved_budget` added to the totals.
- **When over budget.**
  1. Tools are kept in input order.
  2. The first tool that doesn't fit is affected, along with every tool after it.
  3. Without `strict_fallback`, the affected tools go to `rejected` with a `fatal` entry.
  4. With `strict_fallback`, each affected tool is **re-normalized** for the non-strict sibling target, which gives it its own schema and reverse map. It is then emitted with `strict: false` and a `fallback` entry.

### 6.5 Description hints (`spec/hint-format.md`)

```
<original description>\n\n[constraints: exclusiveMinimum=0; pattern="^[A-Z]{2}$"]
```

- The hint always goes at the end of the description.
- Keys are sorted, and values are JCS-encoded.
- If there is no original description, the description is exactly the bracketed hint.
- **Detecting an existing hint** (needed for idempotence): the description must end with a full match of `\n\n\[constraints: …\]`, or consist entirely of the hint, and all values must be valid JCS. If a hint is already present, new constraints merge into it.
- **Placement**:
  - A constraint inside an `anyOf` branch gets its hint on that branch.
  - A constraint that sits next to a `$ref` gets its hint on the `anyOf` wrapper (§6.4.3), or as an annotation-only sibling of the `$ref` (§6.4 S2).
  - A hint on a shared `$def` appears everywhere that `$def` is used. This is intentional and documented.
- **Length limits**:
  - A value longer than 200 characters is truncated with `…`. The report keeps the full original.
  - `max_description_chars` truncates only the original text, never the hint.
- **Cost and claims**: the README publishes how many tokens hints add across the corpus. It makes **no accuracy claim** unless an eval backs it.

### 6.6 Determinism

- **JCS encoder.** We write our own JCS (RFC 8785) encoder and validate it against the RFC test vectors. It ships in the runtime, because hint values depend on it.
  - Keys are sorted by UTF-16 code units.
  - Numbers are formatted with ECMAScript `Number::toString`.
- **Key order in output.**
  - Emitted schemas keep the source order of `properties` and `required`.
  - In v0.2, the parity check compares both the JCS bytes and the order of `properties`/`required`.
  - The TS port stores properties in a `Map`, because plain JS objects reorder integer-like keys. It also guards against `__proto__` keys.
- **Strings.** No Unicode normalization is applied. Names and enum strings are compared exactly.

---

## 7. Corpus, verdicts and adapters

### 7.1 Repository layout

```text
mcp-schema-bridge/
├── rules/<target>.json                  # source of truth for provider rules
├── spec/                                # report/normalized-tool/reverse-map schemas, hint-format, allof-merge, keyword-classes, regex-vectors
├── corpus/
│   ├── manifest.json                    # cases: kind (synthetic|captured), tids covered, pending per language
│   ├── cases/<id>/input.json            # one MCP tool {name, description, inputSchema}
│   ├── cases/<id>/meta.json             # source URL, server version/commit, SPDX license, synthetic: bool
│   ├── cases/<id>/expected.<target>.json   # golden (see below)
│   ├── cases/<id>/verdict.<target>.json    # {raw:{status,error}, normalized:{status,error,sha256}, model, recorded_at}
│   ├── args/<id>.<target>.json          # [{model_args, expected_mcp_args, expected_warnings}]
│   └── toolsets/<id>/{tools.json, expected.<target>.json, verdict.<target>.json}
├── python/
│   ├── pyproject.toml
│   └── src/mcp_schema_bridge/{core/, adapters/, cli/, _rules/}
├── typescript/                          # v0.2: src/{core,adapters,cli}, src/rules.generated.ts
├── scripts/                             # PEP 723 scripts: record_verdicts, probe, capture_server, check_rules_sync,
│                                        #   check_corpus, check_package_contents, check_readme, smoke_installed, parity (v0.2)
├── examples/  docs/  docs/adr/  docs/rules/
└── README.md LICENSE NOTICE REUSE.toml SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md CHANGELOG.md CODEOWNERS
```

**Golden files**
- `expected.<target>.json` is the JCS encoding of the `ToolsetResult` from `normalize_tools([input])`, so the report is covered by the golden as well.
- Before writing or comparing, the harness **removes `fingerprint`, `library_version` and `rules_version`**. A version bump therefore never invalidates goldens or verdict hashes. The harness checks the fingerprint separately.

**Synthetic cases**
- Each one is minimal and hand-written, and covers one rule.
- Its expected file is written **by hand, before the code**. These cases drive TDD.

**Captured cases**
- Expected files are generated with `pytest --update-golden`, only in commits prefixed `corpus:`, and the diff is reviewed.
- They are guarded by invariants (§8.3), not by someone reading them line by line.

**Pending and coverage gates**
- `manifest.json` lists pending work per language, e.g. `pending: {"py": ["T11a"]}`. Those cases run as **strict xfail**, so an unexpected pass fails.
- A release requires every pending list to be empty.
- Coverage gate: every (tid × affected target) has at least one synthetic case and one captured case.

**Licensing**
- Captured schemas are kept only if their license allows redistribution. Otherwise we write a synthetic case that reproduces the same failure.
- SPDX metadata goes in `REUSE.toml` and attribution in `NOTICE`.
- `corpus/` is **excluded from the wheel, sdist and npm tarball**. `check_package_contents.py` enforces this.
- Recorded error text is scrubbed of request ids and org ids.

### 7.2 Verdicts and probes

**Recording (`record_verdicts.py`)**
- Sends one minimal request per (case, target) on the pinned models, forcing the tool choice where allowed and keeping `max_tokens` minimal.
- The **raw** verdict is recorded in Phase 0. The **normalized** verdict is recorded at the end of Phase 2, together with the `sha256` of the stripped golden it tested.
- `--check` mode re-records each verdict and exits non-zero in either case:
  - a status differs from the committed verdict;
  - a normalized case is not `accepted` and isn't an expected `Rejection`.

**Offline tests (no API keys needed)**
1. The rules tables predict every recorded raw accept or reject.
2. Each golden's hash matches its verdict's `sha256`. A mismatch reports "unverified output": a warning on PRs, a failure at release.

**Probes (`probe.py`)** detect constraints that are silently stripped, which acceptance alone can't show.
1. Each probe uses a constraint that would visibly change the output if obeyed, such as a single-value `pattern` or a `const`.
2. A **baseline** run without the constraint must violate it in at least 1 of 5 samples. Otherwise the probe is inconclusive and is redesigned.
3. With the constraint present, the result is:
   - 5/5 compliant → *enforced*;
   - any violation → *stripped*.
4. Results are recorded with `evidence: "probe"`.

### 7.3 Capturing servers

`capture_server.py` is a PEP 723 script that depends on the official `mcp` SDK. It captures `tools/list` once and commits the result.

- **Preferred:** servers that list their tools without credentials.
  - The reference servers: filesystem, git, fetch, memory, everything, time.
  - Playwright.
  - Servers built with Pydantic, FastMCP and Zod.
- **Needs credentials** (GitHub, Notion, Stripe, Postgres): take the schemas from the published source at a pinned commit instead.

### 7.4 SDK adapters (`[sdks]` extra)

| api | Shape |
|---|---|
| `genai` | `FunctionDeclaration(name, description, parameters_json_schema=…)`, with a minimum `google-genai` version pinned |
| `openai-chat` | `{type: "function", function: {name, description, parameters, strict}}` |
| `openai-responses` | `{type: "function", name, description, parameters, strict}` |
| `anthropic-messages` | `{name, description, input_schema, strict}` |

The adapters **always set `strict` explicitly** from `NormalizedTool.strict`. Otherwise the Responses API could apply strict mode to a non-strict schema, which the reverse map doesn't account for.

Tests build real SDK request objects. That proves the request shape is valid. Whether a provider accepts it is proven by the verdicts.

---

## 8. Testing strategy

### 8.1 Layers

1. Unit tests for each stage (S0–S13).
2. Synthetic corpus cases. These drive TDD.
3. Captured corpus cases: goldens plus invariants.
4. Property tests (§8.3).
5. Adapter tests against real SDK types.
6. CLI tests against a fake stdio MCP server fixture (a tiny script that serves a paginated `tools/list`).
7. Live verdicts and probes. These are nightly and release-gated, never part of ordinary CI.

### 8.2 Generators

- **Schemas.** `tests/strategies.py` generates MCP-shaped schemas. Depth is bounded, keyword frequencies come from the corpus, and the generator covers `$defs` reuse, recursion, unions, hostile property names and big numbers.
- **Instances.** A Phase 1 spike checks whether `hypothesis-jsonschema` (test-only) can generate instances for 2020-12 keywords (`prefixItems`, `$defs`) and for recursive `$ref`. Where it can't, `tests/strategies.py` adds a custom instance strategy over our own output subset. That subset is small and known.
- **CI profile.** `derandomize=True` and a pinned `max_examples`.

### 8.3 Properties

Each property runs over the generators *and* over every corpus case.

1. **Idempotence.** For the same target, `normalize_schema(normalize_schema(x).schema)` returns the same schema with no report entries.
2. **Determinism.** The same input always produces byte-identical output, and inputs are never mutated.
3. **Allow-list.** The output uses only keywords and formats the target's rules allow, and it meets the per-schema limits.
4. **No silent loss.**
   - The normalizer emits a **provenance trace**: each output node maps to its source pointer(s).
   - For every *validation* keyword at a source pointer (classed per `spec/keyword-classes.json`), one of these must hold:
     - the same keyword and value appear on a traced output node; or
     - the report has an entry with that `source_path` and `keyword`.
5. **Round-trip.** For every instance `i` that is valid against the normalized schema, `denormalize(i)` must be valid against `relax(original, report)`.
   - `relax` is a separately tested function. It removes or loosens exactly the keywords named in `lossy` entries, and turns `oneOf` into `anyOf` where that conversion was reported.
   - The validity check uses the `jsonschema` package (test-only) with format assertion turned on. `pattern` is excluded from that check.
   - Cases that produce `core/reverse-ambiguous-branch` entries are excluded and counted separately.
6. **Reverse totality.** Generated *invalid* model outputs never crash `denormalize_args`. The result is a warning, or an error when `strict=True`.
7. **Hints.** With `hints=True`, every entry where `action` is `dropped` and the keyword is classed as *validation* has `hinted: true`.

---

## 9. Execution plan

### 9.1 Discipline

**The TDD cycle for every slice**
1. Write the test, or the synthetic case plus its hand-written expected output.
2. **Run it and watch it fail.**
3. Write the minimal code that makes it pass.
4. Commit the test and the code together. The commit body quotes the failing assertion.
5. Refactor in a separate commit.

**Commit and changelog rules**
- Conventional Commits.
- `release-please` writes the changelog, with a separate **"Provider rule updates"** section.
- A slice never mixes a refactor with new behaviour.
- Captured goldens change only in `corpus:` commits.

### Phase 0: Ground truth and go/no-go (about 1.5 weeks; no library code)

- [ ] Review prior art (§2) and contact the closest project. Write ADR-0001 (go or contribute) and ADR-0002 (license).
- [ ] Reserve both package names by publishing a real `0.0.1` to PyPI and npm. Each needs a README stating the intent and must export its `version`. No empty placeholder packages.
- [ ] Check the current MCP trademark and naming guidance for the name.
- [ ] Set up API accounts with dedicated keys and **hard spend caps**. Write `docs/live-verification.md` covering:
  - who pays, and the budget;
  - key rotation;
  - that contributors never need keys.
- [ ] Capture or extract at least 10 servers (§7.3).
- [ ] Build `record_verdicts.py` and `probe.py`. Record **raw** verdicts and probes for every "Open" item in §4.
- [ ] Write `rules/*.json`, with evidence for each row. Correct §4 wherever the APIs disagree with the docs.
- [ ] Resolve D3.

**Exit criteria**
- ADR-0001 says **go**.
- Every rules row has `evidence`, `source_url` and `verified_on`.
- Every Open item in §4 is either answered or marked `unknown → conservative default`.

### Phase 1: Scaffolding and specs (about 1 week)

Each item below is its own slice.

1. **Scaffold the repo.**
   - Tooling: uv with a src layout, ruff, pyright (`typeCheckingMode = "strict"` in pyproject), pytest and hypothesis.
   - Python ≥ 3.11, tested on 3.11–3.14 across ubuntu, macos and windows.
   - Repo files: LICENSE, a minimal README, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, CODEOWNERS, issue templates and dependabot.
   - `ci.yml` with Actions pinned by SHA and least-privilege `permissions:`.
2. **`release.yml`**, proven with a **dry run to TestPyPI**. It uses Trusted Publishing (OIDC), PEP 740 attestations, and a CycloneDX SBOM attached to the GitHub release.
3. **`spec/*` files** (listed in §7.1).
4. **Rules sync.** The script copies `rules/*.json` into `python/src/mcp_schema_bridge/_rules/`. `check_rules_sync.py` fails CI if the copies differ.
5. **Corpus harness.** Includes `manifest.json`, strict xfail, `--update-golden`, golden stripping, `check_corpus.py` (licenses, coverage gate, pending lists) and `check_package_contents.py`.
6. **Spike: can `hypothesis-jsonschema` generate instances for our output?** (§8.2). Record the decision.

### Phase 2: Core (about 7–9 weeks), in slice order

1. JCS encoder, tested against the RFC vectors.
2. S0 parsing and input guards.
3. Report model and its total ordering.
4. **ReverseMap and `denormalize_args`**, plus the `args/` harness. It runs against hand-written `NormalizedTool` fixtures. `unwrap_root` is the first op.
5. Provenance trace and `relax()`. Property 4's skeleton lands here.
6. S1 resolve: dialects, pointer escaping, `$id`/`$anchor`, T2c.
7. S2 canonicalization, including T3.
8. The inlining primitive (used by S3 and S4), then S4 (T2a/T2b). At the recursion cutoff:
   - an **optional** recursive property is removed from `properties` (`truncated`, `lossy`);
   - a **required** recursive property, or a recursive array item, is `fatal`.
9. S3 `allOf` merge, one slice per rule in §6.4.1.
10. S5 root handling and `$ref` rewriting.
11. S6 unions (T8, T9, T5, T4).
12. S7 object closing (T10).
13. S8 optional fields (T11a/T11b).
14. Regex scanner (T16).
15. S9 filter (T1, T12, T13, T15).
16. S10 hints. **All synthetic cases before this slice run with `hints=False`.** Cases that need hints stay `pending` until this slice lands.
17. S11 limits and T18. S12 finalize.
18. S13 toolset budgets, plus re-normalization under `strict_fallback`.
19. Opt-in reverse repairs.
20. Pairwise interaction cases: T7×T9, T9×T11, T2×T11, T14×T2, T10×T17, T5×T11.
21. Record **normalized** verdicts, then fix anything a live API rejects.

**Property tests** (§8.3) land with the earliest slice that makes each one meaningful, and they stay on from then on. Coverage of `mcp_schema_bridge.core` must be at least 95%, and CI enforces that.

### Phase 3: Adapters, CLI and docs (about 2 weeks)

**Adapters**
- As specified in §7.4.

**CLI** (`[cli]` extra; `mcp` SDK for `--stdio`)
- Command: `mcp-schema-bridge check|normalize`.
- Input sources:
  - `FILE`: a single schema or a `tools/list` result, auto-detected.
  - `-`: stdin.
  - `--stdio -- <argv…>`: argv only, never passed through a shell.
- Flags:
  - `--target` (repeatable).
  - `--format json|text`.
  - `--fail-on info|reversible|lossy|fatal`: fails when any entry is at or above the given severity. With several targets, the worst result across them counts.
- JSON output: `{"<target>": {tools, rejected, report}}`.
- Exit codes:
  - `0`: OK.
  - `1`: the `--fail-on` threshold was reached.
  - `2`: usage error.
  - `3`: input, server or timeout error.

**Examples.** `examples/` holds about 30 lines of runnable code per provider loop (Gemini, OpenAI and Anthropic). Each follows the same steps: `ClientSession.list_tools()` → normalize → provider call → `denormalize_args` → `call_tool`.

**Docs site (mkdocs-material)**
- Quickstart.
- One page per target, generated from the rules files.
- One page per rule id.
- Report reference.
- "For framework authors": caching `NormalizedTool`, when to re-normalize, thread safety, and how to surface the report.
- "Migrating from hand-written patches".
- "Why not X?"
- "What we can't fix".

**README**
- A before/after built on a real 400.
- The generated compatibility matrix, showing `verified_on` dates and the models tested.
- Install instructions and a 10-line example.
- Its snippets are tested by `check_readme.py`.
- `docs/claims.md` maps each differentiator claimed in the README to the test or check that proves it.

**Benchmark.** Normalize a real 100-tool toolset for each target and record p50/p99. It runs in CI as a non-blocking report, and the numbers go in the README.

**Manual exit check.** Read the CLI reports for 3 real servers and confirm a human can make sense of them.

### Phase 4: Hardening and the v0.1.0 release (about 1 week)

**`nightly-verdicts.yml`**
- Access and safety:
  - Runs in a GitHub Environment restricted to `main`, with a required reviewer.
  - Never runs on PRs.
  - CODEOWNERS covers `scripts/` and `.github/`.
  - Workflows are linted with zizmor.
  - A kill switch: `vars.LIVE_ENABLED`.
- Cost:
  - The estimate is (cases × targets × 2 + probes) × pinned models × 30 nights. It is documented and stays under the spend caps.
- Drift handling:
  - Updates one open drift issue per target instead of opening a new issue every night.

**Supply chain**
- Branch protection with required review.
- 2FA on both registries.
- OpenSSF Scorecard and its badge.
- A protected release environment.
- Idempotent re-runs, so a partial publish can be finished.

**Policies**
- Runtime support: a runtime is dropped 6 months after its upstream end of life.
- Versioning: see §10.1.
- Deprecations: one minor release of warnings first.

**SECURITY.md**
- The library does no network I/O.
- `--stdio` runs the argv the user supplies.
- No telemetry.
- Input size and depth caps.

**Release.** Ship **v0.1.0** through `release.yml`, only after §11 passes. The live check runs in the protected release environment.

### Phase 5 (v0.2): TypeScript port and deferred features (about 4–6 weeks)

**Tooling**
- pnpm, tsup (ESM + CJS + d.ts), vitest, fast-check, eslint, and `tsc` with `strict: true`.
- Node ≥ 22, tested on 22, 24 and 26.
- An `exports` map and `sideEffects: false`.
- Checked with `publint` and `attw`.
- npm trusted publishing with provenance.
- A `size-limit` budget of 30 KB min+gz, rules included.

**Port**
- `typescript/src/rules.generated.ts`, kept in sync by `check_rules_sync.py`.
- Port slice by slice against the same corpus, using per-language `pending.ts` lists.
- `parity.py` compares JCS output and key order across the whole corpus, and differentially fuzzes both CLIs with hypothesis-generated schemas.

**Features deferred from v0.1**
- The legacy `gemini` target, together with T6.
- Name rewriting.
- T11c.
- `map_as_entries`.
- Rules-snapshot pinning.

**Versioning.** Python and TS versions move in lockstep from v0.2 on.

---

## 10. Packaging and versioning

### 10.1 Versions

**`library_version`** (semver). The meaning of each bump changes at 1.0:

| Bump | Before 1.0 (0.x) | From 1.0 on |
|---|---|---|
| Patch | Bug fixes that change no golden | Same |
| Minor | Any change to the normalized output of an existing corpus case, **including rules-only changes**. Minor releases may break things, and the changelog says so | Same, minus breaking changes |
| Major | n/a | Changes to the API, CLI or report schema |

**`rules_version`** (date-based, `YYYY.MM.DD`)
- Stamped into every report and every `NormalizedTool`.
- Rules changes are listed under "Provider rule updates".

**What 1.0 requires**
- The API and the report schema are stable.
- Both languages have shipped.
- At least one framework integration is running in production.

### 10.2 Rules data in the packages

- The `rules/` folder at the repo root is the source of truth.
- A sync script copies it to `python/src/mcp_schema_bridge/_rules/` and, in v0.2, generates `typescript/src/rules.generated.ts`.
- The copies are committed. `check_rules_sync.py` fails CI if they drift from the source.
- `smoke_installed.py` checks the built packages: it builds the wheel (and later the npm tarball), installs it into a clean virtualenv, and runs `normalize` on a single case.

---

## 11. Verification and Definition of Done (v0.1)

```bash
set -euo pipefail
cd ~/workspace/mcp-schema-bridge
(cd python && uv run ruff check && uv run pyright \
   && uv run pytest -q --cov=mcp_schema_bridge.core --cov-fail-under=95)
uv run --script scripts/check_rules_sync.py
uv run --script scripts/check_corpus.py             # manifest, licenses, coverage gate, empty pending lists
uv run --script scripts/check_package_contents.py   # corpus/ not shipped
uv run --script scripts/check_readme.py             # README snippets run; matrix regenerated == committed
uv run --script scripts/smoke_installed.py          # wheel → clean venv → normalize one case
# CLI end-to-end (needs Node for npx); exit 0 or 1 is fine, 2/3 is a failure:
rc=0; (cd python && uv run --extra cli mcp-schema-bridge check --target gemini-json --target openai-strict \
   --fail-on lossy --stdio -- npx -y @modelcontextprotocol/server-filesystem /tmp) || rc=$?; [ "$rc" -le 1 ]
# Release environment only (needs secrets):
uv run --script scripts/record_verdicts.py --check
```

**Definition of Done.** v0.1.0 ships only when all of these hold:
1. Every command above passes on the release commit. The last one runs in the protected release environment.
2. For every captured case and target, one of these is true:
   - It has a verdict with `normalized.status = accepted`. The verdict was recorded on the pinned models within the last 14 days, and its `sha256` matches the current stripped golden.
   - It has an expected `Rejection` with documented reasons.
3. There are no `flaky` markers, and every `pending` list is empty.
4. Properties 1–7 (§8.3) pass under the CI profile, and coverage of `core` is at least 95%.
5. Every rules row has an evidence type, a source and a `verified_on` date. The README matrix has been regenerated and matches.
6. Every differentiator claimed in the README is mapped in `docs/claims.md` to a passing test or check.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Provider rules change | Rules as data with evidence types; nightly verdicts and probes; `rules_version`; one drift issue per target |
| Existing projects already cover this | Phase 0 review, outreach, and ADR-0001. Contributing to an existing project is an acceptable outcome |
| Schedule slips (about 13–15 weeks to v0.1 for one person: 1.5 + 1 + 7–9 + 2 + 1) | Scope is already cut: Python only, 5 targets, 2 CLI commands. Estimates are re-checked after Phase 0 |
| The round-trip is wrong in edge cases | Reverse anchored at use sites; ambiguous-branch reporting; round-trip and totality properties; fingerprint checks |
| Hints cost tokens or confuse the model | Compact format; `hints=False` option; token cost published; no accuracy claims |
| Live tests are costly, flaky, or leak keys | Spend caps; minimal tokens; nightly or release only; environment-gated secrets; kill switch; scrubbed errors |
| Maintainer bus factor | Live verification documented; verdicts committed; contributors never need keys |
| Trademark or naming issues ("MCP") | Checked in Phase 0 |
