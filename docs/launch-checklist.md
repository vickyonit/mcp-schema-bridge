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

## Needs the maintainer (cannot be done from code)

1. **Anthropic API key.** Run `scripts/probe.py` and `scripts/record_verdicts.py` for `anthropic-strict`,
   then update `rules/anthropic*.json` evidence from `doc`/`reported` to `probe`/`recorded`. OpenAI
   strict and Gemini are already done. Add `OPENAI_API_KEY` to the nightly job's environment as well.
2. **Repository settings:**
   - Branch protection on `main` (required reviews, required CI checks).
   - Private vulnerability reporting.
   - The `live-verification`, `pypi`, `testpypi` and `npm` environments, with a required reviewer on
     the publishing ones.
   - The `GEMINI_API_KEY` secret (a capped key) in `live-verification`.
   - DCO app.
3. **Registries:**
   - Enable 2FA.
   - Add this repository as a trusted publisher on PyPI, TestPyPI and npm.
   - Run `release.yml` with `repository: testpypi` first, to rehearse the release.
4. **Name check.** Review current MCP trademark and branding guidance for using "MCP" in a package name.
5. **Outreach** (ADR-0001). Contact the maintainers of `@mastra/schema-compat`, Pydantic AI, `tool-schema`
   and `mcpschema` before announcing. Re-check the "Related projects" wording against their current
   versions.
6. **Make the repository public.** Add topics (`mcp`, `json-schema`, `gemini`, `openai`, `anthropic`,
   `function-calling`) and a social preview image. Add OpenSSF Scorecard once it is public, because
   Scorecard needs a public repository.
7. **First release.** Merge the release-please PR for `0.1.0`. That tags the release, and both
   packages publish from the tag.
