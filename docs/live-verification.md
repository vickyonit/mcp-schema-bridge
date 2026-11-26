# Live verification

Provider behaviour changes without notice, so rules in `rules/*.json` carry an evidence type:

| Evidence | Meaning |
|---|---|
| `recorded` / `probe` | Observed against the live API by `scripts/record_verdicts.py` / `scripts/probe.py` (files in `corpus/verdicts/` and `evidence/probes/`). |
| `doc` | Cited from official documentation (`source` URL). |
| `reported` | Reported by the community; not yet observed by us. |
| `assumed` | A conservative default where nothing is documented. |

## What is verified today (2026-11-26)

- **Gemini (`gemini-json`)**: acceptance probes and enforcement probes on `gemini-3.5-flash-lite` and
  `gemini-2.5-flash`, plus raw and normalized verdicts for all 116 corpus tools.
- **OpenAI and Anthropic**: documentation and community reports only. The scripts support both
  providers, but no keys have been configured yet. Contributions of recorded verdicts are very welcome.

## Running it

Contributors never need API keys: verdicts are committed, and the offline tests
(`python/tests/test_verdicts.py`) check them. Maintainers re-record with:

```bash
GEMINI_API_KEY=... uv run --script scripts/probe.py --target gemini-json --model gemini-3.5-flash-lite
GEMINI_API_KEY=... uv run --script scripts/record_verdicts.py --target gemini-json --model gemini-3.5-flash-lite
uv run --script scripts/record_verdicts.py --target gemini-json --model gemini-3.5-flash-lite --check  # drift only
```

## Cost and safety

- One verdict run sends 2 requests per corpus tool (about 232 requests), with forced tool calls and
  small `max_tokens`. One probe run sends about 220 requests.
- Use dedicated keys with **hard spend caps** set in the provider console.
- The nightly workflow (`.github/workflows/nightly-verdicts.yml`):
  - runs only on `main`, in the protected `live-verification` environment;
  - never runs on pull requests;
  - can be disabled with the repository variable `LIVE_ENABLED=false`.
- Recorded error text is scrubbed of request ids, organization ids and long tokens before it is written.
