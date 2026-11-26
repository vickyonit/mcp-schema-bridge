# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private vulnerability reporting
("Security" tab → "Report a vulnerability"). We aim to acknowledge reports within 5 working days.

## Threat model

- The library performs **no network I/O**. It never dereferences remote `$ref`s (the MCP
  specification forbids it); such schemas are rejected.
- It never evaluates regular expressions from input schemas; `pattern` values are scanned
  syntactically only.
- Input size is bounded (`max_nodes`, `max_depth`) to prevent resource exhaustion from hostile schemas.
- The CLI's `--stdio -- <argv…>` option starts **the command you pass**, as an argv list (never via a
  shell). Only point it at MCP servers you trust.
- No telemetry is collected.

## Supported versions

Only the latest minor release receives security fixes before 1.0.
