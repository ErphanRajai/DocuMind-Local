import { test, expect } from "@playwright/test";
const model = "qwen3:4b-instruct-2507-q4_K_M";
test.beforeEach(async ({ page }) => {
  let complete = false,
    polls = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const catalogue = {
      models: [
        { name: "llama3.2:3b", installed: true, description: "Installed" },
        { name: model, installed: complete, description: "Multilingual" },
      ],
      directory: "C:\\Models",
      windows_console: true,
      ollama_available: true,
      download_available: true,
    };
    if (path.endsWith("/catalog")) return route.fulfill({ json: catalogue });
    if (path.endsWith("/preview")) {
      const request = route.request().postDataJSON();
      if (request.directory === "C:\\NoSpace")
        return route.fulfill({
          status: 422,
          json: { detail: "Not enough free space. Choose another folder." },
        });
      return route.fulfill({
        json: {
          id: "review",
          model,
          directory: request.directory,
          model_bytes: 2497293803,
          download_bytes: 2497293803,
          free_bytes: 20 * 1024 ** 3,
          copy_bytes: 0,
          restart_required: request.directory !== "C:\\Models",
        },
      });
    }
    if (path.endsWith("/install"))
      return route.fulfill({
        status: 202,
        json: {
          id: "a".repeat(32),
          model,
          state: "queued",
          message: "Opening Command Prompt",
          restart_required: false,
          total: 0,
          completed: 0,
        },
      });
    if (path.includes("/local-models/jobs/")) {
      complete = ++polls >= 2;
      return route.fulfill({
        json: {
          id: "a".repeat(32),
          model,
          state: complete ? "completed" : "running",
          message: complete
            ? "Installed and ready to select"
            : "Downloading fixture",
          restart_required: false,
          total: 100,
          completed: complete ? 100 : 50,
        },
      });
    }
    if (path.endsWith("/models"))
      return route.fulfill({
        json: {
          installed: complete ? ["llama3.2:3b", model] : ["llama3.2:3b"],
        },
      });
    if (path.endsWith("/healthz"))
      return route.fulfill({ json: { status: "healthy" } });
    if (path.endsWith("/workspaces") || path.endsWith("/deleted"))
      return route.fulfill({ json: [] });
    return route.fulfill({ json: { revision: 1 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Model & preferences" }).click();
  await expect(
    page.getByRole("option", { name: `${model} — Not installed`, exact: true }),
  ).toBeAttached();
});
test("missing model previews metadata, installs only on confirmation and becomes selectable", async ({
  page,
}) => {
  let installs = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/local-models/install")) installs++;
  });
  await page.getByRole("combobox", { name: "Model library", exact: true }).selectOption(model);
  await expect(
    page.getByRole("region", { name: "Review model installation" }),
  ).toBeVisible();
  await expect(page.getByText("2.33 GiB", { exact: true })).toHaveCount(2);
  expect(installs).toBe(0);
  await page.getByRole("button", { name: "Install in Command Prompt" }).click();
  await expect(
    page.getByRole("progressbar", { name: "Current model file download" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Use installed model" }).click();
  await expect(
    page.locator(".model-library > p").filter({ hasText: "Answer model:" }),
  ).toContainText(model);
  expect(installs).toBe(1);
});
test("phone destination changes invalidate confirmation and recover from a space error", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("combobox", { name: "Model library", exact: true }).selectOption(model);
  await expect(
    page.getByRole("button", { name: "Install in Command Prompt" }),
  ).toBeVisible();
  await page
    .getByLabel("Model library folder", { exact: true })
    .fill("C:\\NoSpace");
  await expect(
    page.getByRole("button", { name: "Install in Command Prompt" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Review download size & folder" })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toHaveText(
    "Not enough free space. Choose another folder.",
  );
  await page
    .getByLabel("Model library folder", { exact: true })
    .fill("E:\\NewModels");
  await page
    .getByRole("button", { name: "Review download size & folder" })
    .click();
  await expect(
    page.getByText(
      "Restart DocuMind after installation to activate this folder. Existing models are preserved.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
