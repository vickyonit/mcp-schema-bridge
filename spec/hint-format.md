# Description hint format (frozen at v0.1)

When a target cannot enforce a validation constraint, the constraint is removed from the schema and
re-stated in the node's `description`, so the model still sees it.

```
<original description>\n\n[constraints: exclusiveMinimum=0; pattern="^[A-Z]{2}$"]
```

## Rules

1. The hint is a single bracketed block at the **end** of the description:
   `[constraints: ` + entries joined by `"; "` + `]`.
2. Each entry is `<keyword>=<value>` where `<value>` is the RFC 8785 (JCS) encoding of the dropped
   value. Entries are sorted by keyword, then by encoded value (UTF-16 code-unit order).
3. A value whose encoding is longer than 200 characters is cut to 199 characters followed by `…`.
   The report entry always keeps the full original value.
4. With no original description, the description is exactly the bracketed block.
   Otherwise the block is separated from the original text by `\n\n`.
5. **Detection** (idempotence): a description ends in a hint iff it matches
   `^(?:(?P<text>[\s\S]*)\n\n)?\[constraints: (?P<body>.*)\]$` where `body` splits on `"; "` into
   `keyword=value` entries. New entries are merged into an existing block (duplicates removed).
6. `NormalizeOptions.max_description_chars` truncates the **original text only** (ellipsis `…` counted
   within the limit); the hint block is never truncated.
7. Hints are not attached to a `$ref` node on targets that forbid keywords next to `$ref`; the report
   entry then has `hinted: false`.
8. A hint on a shared definition appears everywhere that definition is used (intended).
