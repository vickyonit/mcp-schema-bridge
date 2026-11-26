import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    testTimeout: 60_000,
    coverage: { provider: "v8", include: ["src/core/**"], thresholds: { statements: 95, lines: 95 } },
  },
});
