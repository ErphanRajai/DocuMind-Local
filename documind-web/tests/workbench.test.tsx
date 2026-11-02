import React from "react";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import Home from "../app/page";
import { STORAGE_KEY } from "../lib/workspaces";
import { api, consumeJob } from "../lib/api";
vi.mock("../lib/api", () => ({
  post: (body: unknown) => ({ method: "POST", body: JSON.stringify(body) }),
  api: vi.fn(),
  consumeJob: vi.fn(),
  waitDocuments: vi.fn(async (ids: number[], update: Function) => {
    const docs = ids.map((id) => ({
      id,
      filename: "garden.pdf",
      page_count: 5,
      status: "completed",
    }));
    update(docs);
    return docs;
  }),
}));
const source = {
  id: "S1",
  pdf_id: 1,
  page: 2,
  filename: "garden.pdf",
  excerpt: "Budget: 240 dollars.",
};
const seed = {
  id: "w1",
  title: "Garden notes",
  updated: 1,
  documents: [
    { id: 1, filename: "garden.pdf", status: "completed", page_count: 5 },
  ],
  messages: [],
};
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(STORAGE_KEY, JSON.stringify([seed]));
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.mocked(api).mockImplementation(async (path) =>
    path.endsWith("/models")
      ? { installed: ["llama3.2:3b", "other-model"] }
      : path === "/healthz"
        ? { status: "healthy" }
        : path.endsWith("/upload")
          ? [{ ...seed.documents[0], id: 2 }]
          : { id: "job1" },
  );
  vi.mocked(consumeJob).mockImplementation(async (_, emit) => {
    emit({
      type: "metadata",
      sources: [source],
      source_notice: "Evidence provided",
    });
    emit({
      type: "status",
      message: "Reviewing segment 1 of 2",
      total: 2,
      completed: 1,
    });
    emit({ type: "text", content: "The budget is 240 dollars. [S1]" });
    emit({
      type: "done",
      metrics: {
        contextual_retrieval: true,
        quote_checks: [
          { quote: "Budget: 240 dollars.", verified: true, sources: ["S1"] },
        ],
        pages_reviewed: 5,
        segments_reviewed: 5,
        cache_hits: 2,
        tok_per_sec: 30,
        done_reason: "length",
        warnings: ["OCR may be incomplete"],
        citation_warning: "Check the evidence",
        context_notice: "Older turns omitted",
      },
    });
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});
async function ready() {
  render(<Home />);
  await screen.findByText("Garden notes", { selector: "h1" });
}
async function ask() {
  fireEvent.change(screen.getByRole("textbox", { name: "Ask DocuMind" }), {
    target: { value: "What is the budget?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  await screen.findByText("The budget is 240 dollars.");
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Stop generation" }),
    ).toBeNull(),
  );
}
it("uses saved documents for questions and reveals source pages", async () => {
  await ready();
  await ask();
  expect(
    vi
      .mocked(api)
      .mock.calls.some(
        ([path, options]) =>
          path.endsWith("/jobs") &&
          JSON.parse(options!.body as string).payload.pdf_ids[0] === 1,
      ),
  ).toBe(true);
  fireEvent.click(
    screen.getByRole("button", { name: "Open source S1, PDF page 2" }),
  );
  expect(
    screen.getByRole("img", { name: "Original PDF page 2 of garden.pdf" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Behind this answer")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }));
  expect(
    screen.getByRole("spinbutton", { name: "PDF page number" }),
  ).toHaveValue(3);
  fireEvent.click(screen.getByRole("button", { name: "Previous PDF page" }));
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "PDF page number" }),
    { target: { value: 4 } },
  );
  expect(screen.getByRole("spinbutton")).toHaveValue(4);
});
it("runs distinct complete and quick reviews with coverage details", async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Complete review" }));
  await screen.findByText("The budget is 240 dollars.");
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Stop generation" }),
    ).toBeNull(),
  );
  fireEvent.click(screen.getByText("Evidence & response details"));
  expect(screen.getByText(/5 readable pages/)).toBeInTheDocument();
  expect(screen.getByText(/explicit quotations matched/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Quick overview" }));
  await waitFor(() => expect(vi.mocked(consumeJob)).toHaveBeenCalledTimes(2));
  const requests = vi
    .mocked(api)
    .mock.calls.filter(([p]) => p.endsWith("/jobs"))
    .map(([, options]) => JSON.parse(options!.body as string));
  expect(requests.map((r) => r.payload.mode)).toEqual(["complete", "quick"]);
});
it("shows errors and retries without appending a duplicate user question", async () => {
  vi.mocked(consumeJob).mockRejectedValueOnce(new Error("Model unavailable"));
  await ready();
  await askWithoutWait();
  await screen.findByText("Model unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Retry request" }));
  await screen.findByText("The budget is 240 dollars.");
  expect(
    screen.getAllByText("What is the budget?", { selector: "p" }),
  ).toHaveLength(1);
});
async function askWithoutWait() {
  fireEvent.change(screen.getByRole("textbox", { name: "Ask DocuMind" }), {
    target: { value: "What is the budget?" },
  });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Ask DocuMind" }), {
    key: "Enter",
  });
}
it("stops server work and labels its partial draft", async () => {
  vi.mocked(consumeJob).mockImplementationOnce(async (_, emit, signal) => {
    emit({ type: "text", content: "Partial draft" });
    await new Promise<void>((_, reject) =>
      signal.addEventListener(
        "abort",
        () => reject(new DOMException("Stopped", "AbortError")),
        { once: true },
      ),
    );
  });
  await ready();
  await askWithoutWait();
  await screen.findByText("Partial draft");
  fireEvent.click(screen.getByRole("button", { name: "Stop generation" }));
  await screen.findByText("Stopped draft");
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/job1/cancel")),
  ).toBe(true);
});
it("creates, switches and filters workspaces", async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "New workspace" }));
  expect(
    await screen.findByRole("heading", { name: /A little clarity/ }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Find a workspace" }), {
    target: { value: "Garden" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Garden notes/ }));
  expect(
    screen.getByRole("heading", { name: "Garden notes" }),
  ).toBeInTheDocument();
});
it("opens preferences and selects models and compatible providers", async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Model & preferences" }));
  const modal = screen.getByRole("dialog");
  fireEvent.change(within(modal).getByLabelText("Installed model"), {
    target: { value: "other-model" },
  });
  fireEvent.change(within(modal).getByLabelText("Model source"), {
    target: { value: "openai-compatible" },
  });
  fireEvent.change(within(modal).getByLabelText("Model ID"), {
    target: { value: "remote-model" },
  });
  fireEvent.change(within(modal).getByLabelText("API base URL"), {
    target: { value: "https://example.test/v1" },
  });
  fireEvent.change(within(modal).getByLabelText(/API key/), {
    target: { value: "test-only-key" },
  });
  fireEvent.click(
    within(modal).getByRole("button", { name: "Back to the work" }),
  );
  await ask();
  const call = vi.mocked(api).mock.calls.find(([p]) => p.endsWith("/jobs"))!;
  expect(JSON.parse(call[1]!.body as string).payload.provider).toBe(
    "openai-compatible",
  );
});
it("validates uploads and polls accepted document IDs", async () => {
  await ready();
  const files = screen.getByLabelText("PDF files");
  fireEvent.change(files, {
    target: { files: [new File(["bad"], "bad.txt")] },
  });
  expect(
    await screen.findByText("Choose PDF files up to 50 MB each."),
  ).toBeInTheDocument();
  fireEvent.change(files, {
    target: {
      files: [
        new File(["%PDF-test"], "other.pdf", { type: "application/pdf" }),
      ],
    },
  });
  await screen.findByText("PDFs ready. Ask a question or choose a review.");
  expect(vi.mocked(api).mock.calls.some(([p]) => p.endsWith("/upload"))).toBe(
    true,
  );
});
it("copies answers with quiet feedback", async () => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn(async () => {}) },
  });
  await ready();
  await ask();
  fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
  await screen.findByText("Copied");
});
it("handles page image failure and retry", async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: /garden.pdf/ }));
  fireEvent.error(screen.getByRole("img"));
  expect(
    screen.getByText("This PDF page could not be displayed."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry page" }));
  expect(screen.getByRole("img")).toBeInTheDocument();
});
it("preserves a submitted question when API setup is incomplete", async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Model & preferences" }));
  fireEvent.change(screen.getByLabelText("Model source"), {
    target: { value: "openai-compatible" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Back to the work" }));
  await askWithoutWait();
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByRole("alert")).toHaveTextContent("API key");
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Back to the work" }),
  );
  expect(screen.getByRole("textbox", { name: "Ask DocuMind" })).toHaveValue(
    "What is the budget?",
  );
  expect(vi.mocked(api).mock.calls.some(([p]) => p.endsWith("/jobs"))).toBe(
    false,
  );
});

it("supports the empty state and starter questions", async () => {
  localStorage.clear();
  render(<Home />);
  await screen.findByRole("heading", { name: /A little clarity/ });
  fireEvent.click(
    screen.getByRole("button", { name: "Find the key decisions" }),
  );
  expect(screen.getByRole("textbox", { name: "Ask DocuMind" })).toHaveValue(
    "What are the key decisions and their supporting evidence?",
  );
  fireEvent.change(screen.getByRole("combobox", { name: "Answer length" }), {
    target: { value: "long" },
  });
  expect(screen.getByRole("combobox", { name: "Answer length" })).toHaveValue(
    "long",
  );
});

it("reconnects a saved chat job and restores its completion state", async () => {
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) =>
    path === "/summarizer/workspaces"
      ? [{ ...seed, revision: 1 }]
      : original(path, options),
  );
  sessionStorage.setItem(
    "documind.chat.job",
    JSON.stringify({
      id: "recover-chat",
      workspace: "w1",
      assistant: "restored-answer",
      question: "What is the budget?",
    }),
  );
  render(<Home />);
  await screen.findByText("Recovered completed answer");
  expect(screen.getByText("The budget is 240 dollars.")).toBeInTheDocument();
  await waitFor(() =>
    expect(sessionStorage.getItem("documind.chat.job")).toBeNull(),
  );
});
