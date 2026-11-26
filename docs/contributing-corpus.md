# Adding to the corpus

The corpus is the specification: both implementations must reproduce `corpus/expected/**` exactly.

## A real MCP server

1. Check the server's license allows redistributing its tool schemas.
2. Capture it, pinning the version (the command after `--` is run as an argv list):
   ```bash
   uv run --script scripts/capture_server.py --id my-server --version 1.2.3 \
     --license "MIT" --source https://github.com/org/my-server -- npx -y my-server@1.2.3
   ```
3. Add a `REUSE.toml` annotation and a `NOTICE` line for third-party licenses.
4. Generate goldens in a **separate** commit and review the diff:
   ```bash
   cd python && uv run pytest tests/test_corpus.py --update-golden
   git add ../corpus/expected && git commit -m "corpus: add my-server goldens"
   ```

## A synthetic case

Add `corpus/synthetic/<id>.json` with `{"id", "description", "tool": {name, description, inputSchema}}`,
keeping it minimal: one transformation family per case. Then regenerate goldens as above.

## Coverage

`corpus/manifest.json` lists, for each transformation family (`tid`), the targets whose goldens must
exercise it. `tests/test_corpus.py::test_coverage_gate` enforces this.
