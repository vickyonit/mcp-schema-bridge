# ADR-0002: License under Apache-2.0

- Status: Accepted
- Date: 2026-11-26

## Context

The library is intended to be vendored or depended upon by agent frameworks, some backed by companies with legal review.

## Decision

Apache License 2.0. Contributions are accepted under the Developer Certificate of Origin (DCO, `Signed-off-by:` trailer), not a CLA.

## Consequences

- Explicit patent grant and NOTICE handling.
- Third-party schemas in `corpus/` keep their own licenses, tracked in `REUSE.toml`, and are never shipped in packages.
