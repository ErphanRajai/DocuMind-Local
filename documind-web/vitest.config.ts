import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: [
        "lib/**/*.ts",
        "components/**/*.tsx",
        "app/page.tsx",
        "app/api/**/*.ts",
      ],
      reporter: ["text", "json-summary", "html"],
      thresholds: { statements: 80, branches: 70, functions: 75, lines: 80 },
    },
  },
});
