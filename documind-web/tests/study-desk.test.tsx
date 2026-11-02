import { beforeEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { StudyDesk } from "../components/study-desk";
import { PDFPage } from "../components/pdf-page";
import { api, consumeJob } from "../lib/api";
vi.mock("../lib/api", () => ({
  post: (body: unknown) => ({ method: "POST", body: JSON.stringify(body) }),
  api: vi.fn(),
  consumeJob: vi.fn(),
  waitDocuments: vi.fn(async (ids: number[]) =>
    ids.map((id) => ({ id, filename: "new.pdf", status: "completed" })),
  ),
}));
const workspace = {
  id: "study-one",
  title: "Exam notes",
  documents: [
    { id: 1, filename: "notes.pdf", status: "completed", page_count: 2 },
  ],
  messages: [],
  updated: 1,
  revision: 1,
};
const source = {
  id: "S1",
  pdf_id: 1,
  page: 2,
  filename: "notes.pdf",
  excerpt: "The quadratic formula.",
};
const result = {
  operation: "solve",
  input: {
    operation: "solve",
    expression: "x^2-5*x+6=0",
    variable: "x",
    domain: "real",
  },
  result: "{2,3}",
  latex: "\\{2,3\\}",
  verified: true,
  checks: [{ label: "Substitution", passed: true }],
  steps: ["Factor the polynomial."],
  working_checks: [],
  assumptions: ["Real domain."],
  engine: "SymPy",
};
let rows: any[] = [];
let count = 0;
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  rows = [];
  count = 0;
  vi.stubGlobal(
    "confirm",
    vi.fn(() => true),
  );
  vi.stubGlobal(
    "prompt",
    vi.fn(() => "renamed.pdf"),
  );
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(async () => {}) },
    configurable: true,
  });
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  HTMLAnchorElement.prototype.click = vi.fn();
  vi.mocked(api).mockImplementation(async (path, options) => {
    const data =
      options?.body && typeof options.body === "string"
        ? JSON.parse(options.body)
        : {};
    if (path === "/summarizer/workspaces") return [workspace];
    if (path.includes("/workspaces/")) return { revision: 2 };
    if (path.endsWith("/models"))
      return { installed: ["llama3.2:3b", "other-model"] };
    if (path.includes("/study/items/") && options?.method === "DELETE") {
      rows = rows.filter((i) => !path.includes(i.id));
      return {};
    }
    if (path.includes("/study/items/") && path.endsWith("/review")) {
      rows = [];
      return {};
    }
    if (path === "/summarizer/study/items") {
      const item = { ...data, id: data.id || `item-${++count}` };
      rows = [item, ...rows.filter((i) => i.id !== item.id)];
      return item;
    }
    if (path.includes("/study/items/")) return [...rows];
    if (path.endsWith("/solve")) return result;
    if (path.endsWith("/study/jobs")) return { id: "job-study" };
    if (path.endsWith("/practice")) {
      rows = [
        {
          id: "generated",
          kind: "practice",
          data: { question: "Generated equation", answer: "Checked answer" },
        },
      ];
      return { items: rows };
    }
    if (path.includes("/papers/"))
      return {
        questions: [
          {
            number: "1",
            text: "Question 1 Solve x=3",
            pdf_id: 1,
            page: 1,
            marks: 2,
            subparts: [],
          },
        ],
        notice: "Review detected boundaries",
      };
    if (path.endsWith("/storage"))
      return { review_cache_entries: 5, review_cache_bytes: 200 };
    if (path.endsWith("/trim")) return { removed: 2 };
    if (path.endsWith("/upload"))
      return [{ id: 2, filename: "new.pdf", status: "completed" }];
    if (path.endsWith("/transcribe") || path.endsWith("/vision"))
      return {
        text: "Transcribed equation x=3",
        notice: "Check transcription",
      };
    if (path.includes("/documents/") && options?.method === "PATCH")
      return { ...workspace.documents[0], filename: data.filename };
    return {};
  });
  vi.mocked(consumeJob).mockImplementation(async (_id, emit) => {
    emit({ type: "status", message: "Calculating" });
    emit({
      type: "metadata",
      sources: [source],
      math: result,
      interpretation: { math: result.input },
      retrieval_ms: 15,
      search_queries: 2,
      reranker: "cross-encoder",
    });
    emit({ type: "text", content: "The result is $x=3$. [S1]" });
    emit({ type: "done", metrics: { pipeline_ms: 25 } });
  });
});
async function start() {
  render(<StudyDesk />);
  await screen.findByRole("option", { name: "Exam notes" });
}
function button(name: string | RegExp) {
  return screen.getByRole("button", { name });
}
async function tab(name: string | RegExp) {
  fireEvent.click(button(name));
  await waitFor(() =>
    expect(screen.getByRole("button", { name })).toHaveAttribute(
      "aria-current",
      "page",
    ),
  );
}

it("calculates, checks, copies, exports and saves learning artifacts", async () => {
  await start();
  fireEvent.click(button(/Calculate & check/));
  await screen.findByText("Listed calculation checks passed");
  fireEvent.click(button("Copy LaTeX / answer"));
  await waitFor(() =>
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(result.latex),
  );
  fireEvent.click(button("Export solution"));
  expect(URL.createObjectURL).toHaveBeenCalled();
  fireEvent.click(button("Revisit this problem"));
  await screen.findByText("Saved to this workspace.");
  fireEvent.click(button("Save to formula sheet"));
  await waitFor(() =>
    expect(rows.some((i) => i.kind === "formula")).toBe(true),
  );
  expect(rows.some((i) => i.kind === "attempt")).toBe(true);
});

it("submits explicit operation settings, matrices, units, bounds and working", async () => {
  await start();
  const operation = screen.getByLabelText("Calculation operation");
  fireEvent.change(operation, { target: { value: "matrix" } });
  fireEvent.change(screen.getByLabelText("Square matrix (JSON)"), {
    target: { value: "[[2,0],[0,3]]" },
  });
  fireEvent.change(screen.getByLabelText("Matrix operation"), {
    target: { value: "inverse" },
  });
  fireEvent.click(button(/Calculate & check/));
  await screen.findByText("Listed calculation checks passed");
  expect(
    vi.mocked(api).mock.calls.find((c) => c[0].endsWith("/solve"))?.[1]?.body,
  ).toContain("inverse");
  fireEvent.change(operation, { target: { value: "units" } });
  fireEvent.change(screen.getByLabelText("Value"), { target: { value: "36" } });
  fireEvent.change(screen.getByLabelText("From"), {
    target: { value: "km/h" },
  });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "m/s" } });
  fireEvent.click(button(/Calculate & check/));
  await waitFor(() =>
    expect(
      vi.mocked(api).mock.calls.filter((c) => c[0].endsWith("/solve")).length,
    ).toBe(2),
  );
  fireEvent.change(operation, { target: { value: "integrate" } });
  fireEvent.change(screen.getByLabelText("Lower bound (optional)"), {
    target: { value: "0" },
  });
  fireEvent.change(screen.getByLabelText("Upper bound"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("Variable"), {
    target: { value: "t" },
  });
  fireEvent.change(operation, { target: { value: "check" } });
  fireEvent.change(screen.getByLabelText("Compare with"), {
    target: { value: "2*x" },
  });
  fireEvent.change(operation, { target: { value: "solve" } });
  fireEvent.change(
    screen.getByLabelText("System of equations (optional, one per line)"),
    { target: { value: "x+y=5\nx-y=1" } },
  );
  fireEvent.change(screen.getByLabelText("Domain"), {
    target: { value: "complex" },
  });
  fireEvent.click(button("Fraction"));
  expect(
    (screen.getByLabelText("Equation or expression") as HTMLInputElement).value,
  ).toContain("\\frac");
});

it("runs sourced study jobs and lets users inspect and save the evidence", async () => {
  await start();
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "Explain this equation" },
  });
  fireEvent.change(screen.getByLabelText("Task"), {
    target: { value: "notes" },
  });
  fireEvent.change(screen.getByLabelText("Response"), {
    target: { value: "hint" },
  });
  fireEvent.change(screen.getByLabelText("Local model"), {
    target: { value: "other-model" },
  });
  fireEvent.change(screen.getByLabelText("My working"), {
    target: { value: "x=4" },
  });
  fireEvent.change(screen.getByLabelText("Supplied marking rubric"), {
    target: { value: "Two marks for a correct equation" },
  });
  fireEvent.click(button("Save rubric"));
  await waitFor(() => expect(rows.some((i) => i.kind === "rubric")).toBe(true));
  fireEvent.click(button(/Work this question/));
  await screen.findByText("Study answer complete");
  expect(consumeJob).toHaveBeenCalled();
  fireEvent.click(button("Open source S1, PDF page 2"));
  await screen.findByText("notes.pdf · p. 2");
  fireEvent.click(button("Bookmark page"));
  await waitFor(() =>
    expect(rows.some((i) => i.kind === "bookmark")).toBe(true),
  );
  fireEvent.click(button("Close source"));
  fireEvent.click(button("Edit in calculator"));
  expect(
    (screen.getByLabelText("Equation or expression") as HTMLInputElement).value,
  ).toBe(result.input.expression);
});

it("navigates exam questions, preserves edits, and records attempts", async () => {
  await start();
  await tab("Exam paper");
  fireEvent.change(screen.getByLabelText("Exam PDF"), {
    target: { value: "1" },
  });
  await screen.findByText("Question 1");
  fireEvent.click(button(/Question 1/));
  fireEvent.change(screen.getByLabelText("Selected exam question"), {
    target: { value: "Question 1 Solve x=4" },
  });
  fireEvent.click(button("Mark attempted"));
  await waitFor(() =>
    expect(rows.some((i) => i.data.status === "Attempted")).toBe(true),
  );
  fireEvent.click(button("Mark checked"));
  await waitFor(() =>
    expect(rows.some((i) => i.data.status === "Checked")).toBe(true),
  );
  fireEvent.click(button(/Open in solver/));
  expect(screen.getByLabelText("Your question")).toHaveValue(
    "Question 1 Solve x=4",
  );
});

it("generates checked practice and schedules recall from actual attempts", async () => {
  rows = [
    {
      id: "review-one",
      kind: "mistake",
      data: {
        question: "A saved problem",
        answer: "Recall answer",
        due: "2020-01-01",
      },
    },
  ];
  await start();
  await tab(/^Review queue/);
  fireEvent.click(screen.getByText("Reveal saved answer"));
  expect(screen.getByText("Recall answer")).toBeInTheDocument();
  fireEvent.click(button("Needs another look"));
  await screen.findByText(/No reviews due/);
  fireEvent.change(screen.getByLabelText("Practice topic"), {
    target: { value: "integral" },
  });
  fireEvent.click(button(/Build checked practice/));
  await screen.findByText("Generated equation");
  fireEvent.click(button(/Recalled correctly/));
  await screen.findByText(/No reviews due/);
});

it("manages library notes, search, document links, caches and workspace names", async () => {
  await start();
  await tab("Study library");
  fireEvent.change(screen.getByLabelText("Kind"), {
    target: { value: "annotation" },
  });
  fireEvent.change(screen.getByLabelText("Note (Markdown / LaTeX)"), {
    target: { value: "Remember $x^2$" },
  });
  fireEvent.click(button("Save note"));
  await screen.findByText("Remember $x^2$");
  fireEvent.change(screen.getByLabelText("Search saved study work"), {
    target: { value: "Remember" },
  });
  fireEvent.click(screen.getByText("Open saved work"));
  fireEvent.click(button("Remove saved item"));
  await waitFor(() => expect(rows.length).toBe(0));
  fireEvent.click(screen.getByText("Documents & workspace storage"));
  fireEvent.click(button("Rename"));
  await screen.findByText("renamed.pdf");
  fireEvent.click(button("Reindex"));
  await screen.findByText("Reindexing started. The original PDF is retained.");
  fireEvent.click(button("Trim excess cache"));
  await screen.findByText("2 excess cache entries removed.");
  fireEvent.click(button("Clear review cache"));
  fireEvent.click(button("Rename workspace"));
  fireEvent.click(button("Remove from workspace"));
  await screen.findByText(/Removed from this workspace/);
  fireEvent.click(button("New study workspace"));
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(
          (c) => c[0].includes("/workspaces/") && c[1]?.method === "PUT",
        ),
    ).toBe(true),
  );
});

it("shows failures instead of treating them as completed answers", async () => {
  await start();
  vi.mocked(consumeJob).mockImplementation(async (_id, emit) => {
    emit({ type: "text", content: "Incomplete draft" });
    emit({ type: "error", message: "Model unavailable" });
  });
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "Solve a problem" },
  });
  fireEvent.click(button(/Work this question/));
  await screen.findByRole("alert");
  expect(screen.getByText("Model unavailable")).toBeInTheDocument();
  expect(rows.filter((i) => i.kind === "attempt")).toHaveLength(0);
  fireEvent.click(button("Dismiss error"));
});

it("recovers journaled output after reload", async () => {
  sessionStorage.setItem(
    "documind.study.job",
    JSON.stringify({
      id: "recover",
      workspace: "study-one",
      question: "Previous question",
      task: "notes",
      mode: "answer",
    }),
  );
  await start();
  await screen.findByText("Recovered completed answer");
  expect(screen.getByLabelText("Your question")).toHaveValue(
    "Previous question",
  );
});

it("uploads PDFs and transcribes images with explicit review", async () => {
  const { container } = render(<StudyDesk />);
  await screen.findByRole("option", { name: "Exam notes" });
  fireEvent.change(
    container.querySelector('input[accept="application/pdf"]')!,
    {
      target: {
        files: [new File(["pdf"], "new.pdf", { type: "application/pdf" })],
      },
    },
  );
  await screen.findByText("PDFs ready");
  const imageInput = container.querySelector(
    'input[accept="image/png,image/jpeg"]',
  )!;
  fireEvent.change(imageInput, {
    target: {
      files: [new File(["image"], "question.png", { type: "image/png" })],
    },
  });
  await screen.findByText("Check transcription");
  expect(screen.getByLabelText("Your question")).toHaveValue(
    "Transcribed equation x=3",
  );
  fireEvent.click(screen.getByLabelText(/Use the selected vision model/));
  fireEvent.change(imageInput, {
    target: {
      files: [new File(["vision"], "diagram.png", { type: "image/png" })],
    },
  });
  await waitFor(() =>
    expect(
      vi.mocked(api).mock.calls.some((c) => c[0].endsWith("/vision")),
    ).toBe(true),
  );
});

it("imports backups separately and permits explicit workspace removal", async () => {
  const { container } = render(<StudyDesk />);
  await screen.findByRole("option", { name: "Exam notes" });
  const file = new File(["backup"], "backup.json", {
    type: "application/json",
  });
  Object.defineProperty(file, "text", {
    value: async () =>
      JSON.stringify({
        workspace,
        items: [{ kind: "formula", data: { title: "Imported formula" } }],
      }),
  });
  fireEvent.change(
    container.querySelector('input[accept="application/json"]')!,
    { target: { files: [file] } },
  );
  await screen.findByRole("option", { name: "Exam notes (imported)" });
  await screen.findByText(/Backup imported as a separate workspace/);
  await tab("Study library");
  fireEvent.click(screen.getByText("Documents & workspace storage"));
  fireEvent.click(button("Remove workspace"));
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(
          (c) => c[0].includes("/workspaces/") && c[1]?.method === "DELETE",
        ),
    ).toBe(true),
  );
});

it("migrates browser work when the server is empty", async () => {
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) =>
    path === "/summarizer/workspaces" ? [] : original(path, options),
  );
  localStorage.setItem("documind.workspaces.v2", JSON.stringify([workspace]));
  await start();
  expect(
    vi
      .mocked(api)
      .mock.calls.some(
        (c) => c[0].includes("/workspaces/study-one") && c[1]?.method === "PUT",
      ),
  ).toBe(true);
});

it("stops a model job without saving a completed attempt", async () => {
  vi.mocked(consumeJob).mockImplementation(
    (_id, _emit, signal) =>
      new Promise((_resolve, reject) =>
        signal.addEventListener("abort", () =>
          reject(new DOMException("Stopped", "AbortError")),
        ),
      ),
  );
  await start();
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "Solve something" },
  });
  fireEvent.click(button(/Work this question/));
  await screen.findByRole("button", { name: "Stop" });
  fireEvent.click(button("Stop"));
  await screen.findByText("Stopped draft — incomplete");
  expect(rows.filter((i) => i.kind === "attempt")).toHaveLength(0);
});

it("renders selectable PDF words, regions, search, and accessible text", async () => {
  vi.mocked(api).mockResolvedValue({
    text: "A mathematical definition",
    words: [{ x: 0.1, y: 0.2, w: 0.3, h: 0.04, text: "Definition" }],
    highlights: [{ x: 0.1, y: 0.2, w: 0.3, h: 0.04 }],
  });
  const error = vi.fn();
  const { container } = render(
    <PDFPage
      id={1}
      page={2}
      filename="notes.pdf"
      excerpt="A definition"
      onError={error}
    />,
  );
  await screen.findByText("Definition");
  expect(container.querySelector("mark")).not.toBeNull();
  fireEvent.change(screen.getByLabelText("Find on this PDF page"), {
    target: { value: "triangle" },
  });
  await waitFor(() =>
    expect(
      vi.mocked(api).mock.calls.some((c) => c[0].includes("search=triangle")),
    ).toBe(true),
  );
  fireEvent.error(screen.getByRole("img"));
  expect(error).toHaveBeenCalled();
});
