# Contributing

Thanks for helping! This project is strict about two things: **test-driven development** and
**evidence for provider rules**.

## Ground rules

1. **TDD.** Write the failing test (or corpus case) first, run it, watch it fail, then make it pass.
   Commit the test together with the code. Refactors go in separate commits.
2. **One logical change per commit**, using [Conventional Commits](https://www.conventionalcommits.org/).
3. **DCO.** Sign off every commit (`git commit -s`). By signing off you certify the
   [Developer Certificate of Origin](https://developercertificate.org/).
4. **Never hand-type provider facts** into code or docs. Provider behaviour lives in `rules/*.json`,
   each row with `evidence`, `source_url` and `verified_on`.

## Development

```bash
cd python
uv sync
uv run pytest
uv run ruff check && uv run ruff format --check . && uv run pyright
```

## Adding a corpus case

See [docs/contributing-corpus.md](docs/contributing-corpus.md).

## Updating a provider rule

Open a "Provider drift" issue with the request/response that shows the new behaviour, then update
the row in `rules/<target>.json` (including `evidence` and `verified_on`) and regenerate goldens in a
separate `corpus:` commit.
