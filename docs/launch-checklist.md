# Launch checklist

## Done in the repository

- [x] Python package: pipeline, `normalize_tools`, `denormalize_args`, SDK adapters, CLI
- [x] TypeScript package with output byte-identical to Python (corpus, committed fuzz goldens, CI differential fuzz)
- [x] Golden corpus:
  - 10 captured sources (8 public MCP servers, plus Pydantic and Zod generator output)
  - 45+ synthetic cases
  - argument round-trip goldens
- [x] Live evidence:
  - Gemini: acceptance and enforcement probes on two models; verdicts for every corpus tool
  - OpenAI strict: verdicts for every corpus tool (`gpt-4.1-mini`) and regex probes
- [x] Persona walkthroughs (server builder, client builder in Python and TS, end user with gemini-cli),
  run for real, with fixes recorded in `docs/personas/friction-log.md`
- [x] `mcp-schema-bridge proxy` for end users; how-to guide (`docs/how-to.md`)
- [x] CI:
  - Python 3.11–3.14 on Linux, macOS and Windows; Node 22/24/26
  - lint, strict type checks, coverage at least 95%
  - package contents, installed-wheel smoke test
  - npm `publint`/`attw`, size budget
  - workflow security lint (zizmor)
- [x] Release workflows:
  - PyPI trusted publishing with PEP 740 attestations, SBOM and provenance
  - npm trusted publishing with provenance
  - release-please changelog with both packages in lockstep
- [x] Nightly live-verdict workflow (protected environment, kill switch, one drift issue per target)
- [x] Docs: README with generated compatibility matrix, rule catalog, framework-author guide, live-verification guide, ADRs

- [x] Repository public, with topics and description; private vulnerability reporting on
- [x] Environments `live-verification`, `pypi`, `testpypi`, `npm` (publishing ones need the maintainer's
  approval and only deploy from `main` or `v*.*.*` tags); branch protection on `main` (required checks,
  no force pushes)
- [x] release-please opens the release PR and dispatches `release.yml` / `release-npm.yml` when it is merged

## Needs the maintainer (cannot be done from code)

1. **Registries** (needs your logins):
   - PyPI and TestPyPI → Account → Publishing → add a *pending* trusted publisher: owner `vickyonit`,
     repository `mcp-schema-bridge`, workflow `release.yml`, environment `pypi` (TestPyPI: `testpypi`).
   - npm: the package must exist before trusted publishing can be configured. Either publish 0.1.0 once
     from your machine, or create it and add trusted publisher `vickyonit/mcp-schema-bridge`,
     workflow `release-npm.yml`, environment `npm`. Enable 2FA on both registries.
   - Rehearse: run `release.yml` manually with `repository: testpypi`.
2. **First release.** Merge release PR #1 (`chore(main): release 0.1.0`) and approve the `pypi` and `npm`
   deployments when GitHub asks.
3. **Secrets.** `GEMINI_API_KEY` and `OPENAI_API_KEY` (spend-capped) in the `live-verification` environment
   for the nightly verdicts. An Anthropic key to move `rules/anthropic*.json` evidence to `probe`/`recorded`.
4. **Name check.** Review current MCP trademark and branding guidance for using "MCP" in a package name.
5. **Outreach** (ADR-0001). Contact the maintainers of `@mastra/schema-compat`, Pydantic AI, `tool-schema`
   and `mcpschema` before announcing.
6. **Polish.** Social preview image; OpenSSF Scorecard (now possible, the repository is public); DCO app.
