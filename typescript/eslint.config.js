import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "coverage/**"] },
  ...tseslint.configs.strict,
  {
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
);
