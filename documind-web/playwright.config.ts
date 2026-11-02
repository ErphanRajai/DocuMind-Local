import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: process.env.DOCUMIND_TEST_URL || "http://127.0.0.1:4317",
    channel: process.env.CI ? undefined : "msedge",
    trace: "retain-on-failure",
  },
  fullyParallel: false,
  reporter: "list",
});
