import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      // Generated. The schema is the source of truth and the drift check is the
      // gate; style rules here would be noise on code nobody edits.
      "src/generated/**",
      "coverage/**",
    ],
  },

  js.configs.recommended,

  // TYPE-AWARE rules apply ONLY to files inside the tsconfig project.
  // `projectService` requires every file it lints to belong to a project, and
  // tsconfig.json includes just src/**/*.ts. Pointing type-aware linting at
  // config files, build scripts, or tests fails with
  // "was not found by the project service".
  {
    files: ["src/**/*.ts"],
    extends: [...tseslint.configs.recommendedTypeChecked],
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

  // Everything outside the tsconfig project: syntax-level rules, no type info.
  {
    files: ["*.mjs", "*.js", "*.ts", "scripts/**/*.{mjs,js}", "test/**/*.ts"],
    extends: [...tseslint.configs.recommended],
    languageOptions: { globals: { ...globals.node } },
    rules: {
      // Build scripts report progress on stderr by design.
      "no-console": "off",
      eqeqeq: ["error", "always"],
    },
  },
);
