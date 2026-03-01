const reactHooksStub = {
  rules: {
    "exhaustive-deps": {
      meta: { type: "suggestion", schema: [] },
      create() { return {}; },
    },
  },
};

export default [
  { ignores: ["dist"] },
  {
    files: ["**/*.{js,jsx}"],
    linterOptions: { reportUnusedDisableDirectives: false },
    plugins: { "react-hooks": reactHooksStub },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
      },
    },
    rules: {
      "no-unused-vars": "off",
      "react-hooks/exhaustive-deps": "off",
    },
  },
];
