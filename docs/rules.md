# Rule ids

Every report entry has a stable `rule` id. Ids starting with `core/` behave the same for every target.
Ids starting with `<target>/` (for example `openai-strict/optional-to-nullable`) depend on that target's
rules in [`rules/`](../rules/). The `tid` field groups rules into transformation families (T1–T18, see
[PLAN.md §6.4](PLAN.md)). Severity is listed as the usual value; a few rules vary with context.

## Input, references and dialects

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/identity-keyword-removed` | T1 | info | `$schema`, `$id`, `$anchor` and similar keywords were resolved and removed. The output always uses 2020-12 semantics. |
| `core/big-int-rounded` | T1 | lossy | With `big_int="round"`, an integer outside ±(2^53−1) was rounded to the nearest double. |
| `core/unresolvable-ref` | T2c | fatal | A `$ref` is remote or does not resolve. Remote schemas are never fetched. |
| `core/dynamic-ref-unsupported` | T2c | fatal | `$dynamicRef` / `$recursiveRef` are not supported by any target. |
| `core/unused-def-pruned` | T1 | info | A definition no longer referenced from the output was removed. |
| `core/draft07-ref-sibling-ignored` | T3 | info | In draft-07, keywords next to `$ref` are ignored by definition, so they were removed. |
| `core/tuple-items-to-prefix-items` | T3 | info | Array-form `items` (draft-07) was rewritten as `prefixItems`/`items`. |
| `core/dependencies-split` | T3 | info | `dependencies` was split into `dependentRequired` / `dependentSchemas`. |
| `core/openapi-nullable` | T3 | info | OpenAPI `nullable` was folded into the type array. |
| `core/boolean-subschema` | T3 | info | A `true`/`false` subschema was rewritten as an equivalent object schema. |

## References and recursion

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/root-ref-inlined` | T2b | info | A root-level `$ref` was replaced by its target. |
| `core/ref-with-siblings-inlined` | T2b | info | The target forbids keywords next to `$ref`, so the (non-recursive) reference was inlined. |
| `core/ref-sibling-dropped` | T2b | lossy / info | The target forbids keywords next to `$ref` and the reference is recursive, so the siblings were dropped. |
| `core/unsatisfiable-recursion` | T2a | fatal | Recursion passes only through required, non-nullable positions, so no finite value exists. |
| `core/recursion-truncated` | T2a | lossy / fatal | On a target without recursion, unrolling stopped at `max_ref_depth`. The nearest optional property or union branch was removed (lossy). If none exists, the tool is rejected (fatal). |

## allOf merge (T7)

| Rule | Severity | Meaning |
|---|---|---|
| `core/allof-merged` | info | `allOf` was merged into a single schema. |
| `core/allof-ref-inlined` | info | A `$ref` inside `allOf` was resolved before merging. |
| `core/allof-value-merged` | info | A value changed by combining branches (e.g. `minimum` took the larger value). |
| `core/allof-property-forbidden` | info | A property forbidden by another branch's `additionalProperties: false` was removed. |
| `core/allof-conflicting-pattern` | lossy | Two different `pattern`s; the first was kept and the second hinted. |
| `core/allof-conflicting-multipleof` | lossy | Two different `multipleOf`s; the first was kept and the second hinted. |
| `core/allof-conflicting-format` | lossy | Two different `format`s; the first was kept and the second hinted. |
| `core/allof-conflicting-subschema` | lossy | `not`, `if/then/else` or a similar keyword appears in several branches; the first was kept. |
| `core/allof-first-wins` | info / lossy | Another keyword differs between branches; the first value was kept. |
| `core/allof-two-refs` | lossy | Two different `$ref`s in one `allOf`. |
| `core/allof-ref-cycle` | fatal | `allOf` references itself. |
| `core/allof-unsatisfiable` | fatal | The branches cannot all hold (disjoint types or values, a required property that is forbidden, `false`). |
| `core/allof-distribution-too-large` | fatal | Distributing unions inside `allOf` would exceed `max_nodes`. |

## Unions, enums and types (T4, T5, T8, T9)

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/oneof-to-anyof` | T8 | info / lossy | `oneOf` was rewritten as `anyOf`. This is info when the branches are provably disjoint and lossy otherwise. |
| `core/anyof-siblings-distributed` | T9 | info | Keywords next to `anyOf` were moved into each branch. |
| `core/unsatisfiable-branch-removed` | T9 / T7 | info | A union branch that can never match was removed. |
| `core/unsatisfiable-union` | T9 / T7 | fatal | No branch of a union can match. |
| `core/enum-type-inferred` | T5 | info | `type` was inferred from `enum`/`const` values. |
| `core/mixed-enum-split` | T5 | info | An enum with values of several types became one typed enum per type. |
| `core/const-to-enum` | T5 | info | `const` became an equivalent single-value `enum`, because the target enforces `enum` but not `const`. |
| `core/non-primitive-enum` | T5 | lossy | The target only allows primitive enum values. |
| `<target>/non-primitive-enum` | T12 | lossy | The same, detected by the keyword filter on a typed schema. |
| `core/multi-type-split` | T4 | info | `type: [A, B]` became `anyOf` with type-specific keywords per branch. |
| `core/integer-number-collapsed` | T4 | info | `[integer, number]` became `number`. |

## Objects and optional properties (T10, T11)

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/object-closed` | T10 | info / lossy | `additionalProperties: false` was added (lossy if the object was explicitly open). |
| `core/parameterless-tool-closed` | T10 | info | A tool with no parameters was closed as `{properties: {}, additionalProperties: false}`. |
| `core/open-object-unsupported` | T10 | fatal | A map or open object cannot be expressed in strict mode. |
| `core/any-value-unsupported` | T10 | fatal | A schema that accepts any value cannot be expressed in strict mode. |
| `<target>/optional-to-nullable` | T11a | reversible | An optional property was made required and nullable. `denormalize_args` removes the `null` again. |
| `<target>/optional-nullable-ambiguous` | T11b | lossy | The property was already nullable, so "omitted" and "null" can no longer be told apart. |

## Keyword filter and hints (T1, T12, T13, T15, T16)

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/annotation-dropped` | T1 | info | An annotation or extension keyword the target does not accept was removed. |
| `<target>/keyword-not-enforced` | T12 | lossy | The target accepts the keyword but silently ignores it (e.g. Gemini `pattern`). It was removed and hinted. |
| `<target>/keyword-rejected` | T12 | lossy | The target rejects the keyword (400). It was removed and hinted. |
| `<target>/keyword-unsupported` | T12 | lossy | The keyword is not in the target's supported set. It was removed and hinted. |
| `<target>/integer-exclusive-bound` | T12 | info | For integers, `exclusiveMinimum: n` became the equivalent `minimum: n+1` (and similarly for maximum). |
| `<target>/min-items-clamped` | T12 | lossy | `minItems` was clamped to a value the target supports; the original was hinted. |
| `<target>/default-dropped` | T13 | info | `default` is not supported; it was restated as a hint. |
| `<target>/format-unsupported` | T15 | lossy | The `format` is not enforced by the target; it was removed and hinted. |
| `<target>/pattern-unsupported` | T16 | lossy | The `pattern` uses regex features the target rejects; it was removed and hinted. |
| `core/description-truncated` | T1 | info | The description was truncated to `max_description_chars`. |

## Root, limits, names and toolsets (T14, T17, T18)

| Rule | tid | Severity | Meaning |
|---|---|---|---|
| `core/root-wrapped` | T14 | reversible | The root was wrapped as `{value: …}`. `denormalize_args` unwraps it. |
| `core/root-type-object-added` | T14 | info | The root declared no type; `type: object` was added. |
| `core/root-type-narrowed` | T14 | info | Non-object root types were removed (MCP arguments are always objects). |
| `<target>/array-items-added` | T18 | info | An array without `items` got the equivalent `items: {}`. |
| `<target>/array-items-missing` | T18 | fatal | An array without `items` cannot be expressed in strict mode. |
| `<target>/property-key-invalid` | T18 | fatal | A property name does not match the target's allowed pattern. |
| `<target>/tool-name-invalid` | T18 | fatal | The tool name does not match the target's allowed pattern. |
| `core/duplicate-tool-name` | T18 | fatal | The same tool name appears twice in the toolset. |
| `<target>/limit-max-properties` | T18 | fatal | The total number of properties exceeds the target's limit. |
| `<target>/limit-max-nesting-depth` | T18 | fatal | The object nesting depth exceeds the target's limit. |
| `<target>/limit-max-total-string-chars` | T18 | fatal | The total length of names and enum/const values exceeds the limit. |
| `<target>/limit-max-enum-values` | T18 | fatal | The total number of enum values exceeds the limit. |
| `<target>/limit-max-large-enum-chars` | T18 | fatal | A large string enum is too long in total. |
| `<target>/request-budget-exceeded` | T17 | fatal | The per-request strict budget (tools, optional or union parameters) is exhausted. This tool and all later ones are affected. |
| `<target>/strict-fallback` | T17 | lossy | `strict_fallback` demoted the tool to the non-strict sibling target. |

## denormalize_args warnings

| Rule | Severity | Meaning |
|---|---|---|
| `core/reverse-unrecognized-shape` | lossy | The arguments did not have the expected shape (e.g. a missing `value` wrapper). They were passed through unchanged, or an error is raised with `strict=True`. |
| `core/repair-int-from-float` | info | Opt-in repair: an integral float was converted to an integer. |
| `core/repair-enum-case` | info | Opt-in repair: a unique case-insensitive enum match was applied. |
