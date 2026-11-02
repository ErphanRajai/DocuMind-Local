import { test, expect } from "@playwright/test";
const source = {
  id: "S1",
  pdf_id: 1,
  page: 2,
  filename: "synthetic.pdf",
  excerpt: "The approved budget is 240 dollars.",
};
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path.endsWith("/healthz")) return json({ status: "healthy" });
    if (path.endsWith("/models")) return json({ installed: ["llama3.2:3b"] });
    if (path.endsWith("/preload")) return json({ status: "warming" });
    if (path.endsWith("/upload"))
      return json([
        { id: 1, filename: "synthetic.pdf", page_count: 3, status: "pending" },
      ]);
    if (path.endsWith("/documents/1"))
      return json({
        id: 1,
        filename: "synthetic.pdf",
        page_count: 3,
        status: "completed",
      });
    if (path.endsWith(".png"))
      return route.fulfill({
        contentType: "image/png",
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jh1sAAAAASUVORK5CYII=",
          "base64",
        ),
      });
    if (path.endsWith("/jobs")) return json({ id: "browser-test-job" });
    if (path.endsWith("/events"))
      return route.fulfill({
        contentType: "application/x-ndjson",
        body: [
          { type: "metadata", sources: [source] },
          { type: "text", content: "The approved budget is 240 dollars. [S1]" },
          { type: "done", metrics: {} },
        ]
          .map((e) => JSON.stringify(e) + "\n")
          .join(""),
      });
    return json({});
  });
  await page.goto("/");
});
test("upload, answer, source page and saved conversation", async ({ page }) => {
  await page.getByLabel("PDF files").setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-synthetic"),
  });
  await expect(
    page.getByText("PDFs ready. Ask a question or choose a review."),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask DocuMind" })
    .fill("What is the budget?");
  await page.getByRole("button", { name: "Send question" }).click();
  await page.getByRole("button", { name: "Hide PDF panel" }).click();
  await expect(page.getByRole("region", { name: "PDF evidence" })).toBeHidden();
  await page
    .getByRole("button", { name: "Open source S1, PDF page 2" })
    .click();
  await expect(
    page.getByRole("img", { name: "Original PDF page 2 of synthetic.pdf" }),
  ).toHaveAttribute("src", /pages\/2.png$/);
  await expect(
    page.getByRole("button", { name: "Hide PDF panel" }),
  ).toHaveAttribute("aria-expanded", "true");
  await expect
    .poll(async () =>
      page.evaluate(() =>
        JSON.stringify(localStorage.getItem("documind.workspaces.v2")).includes(
          "The approved budget is 240 dollars.",
        ),
      ),
    )
    .toBe(true);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Open source S1, PDF page 2" }),
  ).toBeVisible();
});
test("mobile separates chat and evidence without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  await page.getByRole("button", { name: "PDF & evidence" }).click();
  await expect(page.getByText("Keep the evidence close.")).toBeVisible();
  await page.getByRole("button", { name: "Close PDF panel" }).click();
  await expect(
    page.getByRole("textbox", { name: "Ask DocuMind" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "PDF & evidence" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "PDF & evidence" }).click();
  await expect(page.getByText("Keep the evidence close.")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Conversation", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Ask DocuMind" }),
  ).toBeVisible();
});
test("mobile keyboard citation opens and focuses the page context", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  await page.getByLabel("PDF files").setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-synthetic"),
  });
  await expect(
    page.getByText("PDFs ready. Ask a question or choose a review."),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask DocuMind" })
    .fill("What is the budget?");
  await page.getByRole("button", { name: "Send question" }).click();
  const citation = page.getByRole("button", {
    name: "Open source S1, PDF page 2",
  });
  await citation.focus();
  await citation.press("Enter");
  await expect(
    page.getByRole("heading", { name: "synthetic.pdf, PDF page 2" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Conversation", exact: true }).click();
  await citation.focus();
  await citation.press("Enter");
  await expect(
    page.getByRole("heading", { name: "synthetic.pdf, PDF page 2" }),
  ).toBeFocused();
});

test("PDF panel closes into a wider conversation and reopens on the same page", async ({
  page,
}) => {
  await page
    .getByLabel("PDF files")
    .setInputFiles({
      name: "synthetic.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-synthetic"),
    });
  await expect(
    page.getByText("PDFs ready. Ask a question or choose a review."),
  ).toBeVisible();
  await page.getByLabel("PDF page number").fill("2");
  const before = await page.locator(".conversation").boundingBox();
  await page.getByRole("button", { name: "Close PDF panel" }).click();
  const opener = page.getByRole("button", { name: "Show PDF panel" });
  await expect(opener).toBeFocused();
  await expect(opener).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("region", { name: "PDF evidence" })).toBeHidden();
  expect(
    (await page.locator(".conversation").boundingBox())!.width,
  ).toBeGreaterThan(before!.width);
  await opener.press("Enter");
  await expect(
    page.getByRole("region", { name: "PDF evidence" }),
  ).toBeVisible();
  await expect(page.getByLabel("PDF page number")).toHaveValue("2");
});

test("settings uses keyboard escape and keeps keys out of storage", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Model & preferences" }).click();
  await page.getByLabel("Model source").selectOption("openai-compatible");
  await page.getByLabel("API key", { exact: false }).fill("synthetic-only-key");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(
    "synthetic-only-key",
  );
});
