import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";




export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "src/generated/**", "coverage/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.node },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-unnecessary-condition": "off",
      "no-console": ["error", { allow: ["error", "warn"] }],
      eqeqeq: ["error", "always"],
    },
  },
);