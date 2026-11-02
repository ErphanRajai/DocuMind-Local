import { beforeEach, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExamRunner } from "../components/exam-runner";
import { Answer, mathMarkdown } from "../components/answer";
import { api, consumeJob, waitDocuments } from "../lib/api";
vi.mock("../lib/api", () => ({
  api: vi.fn(),
  post: (body: unknown) => ({ method: "POST", body: JSON.stringify(body) }),
  consumeJob: vi.fn(),
  waitDocuments: vi.fn(),
}));
const documents = [{ id: 1, filename: "study-fa.pdf", status: "completed" }];
const props = {
  workspaceId: "w",
  paper: 2,
  documents,
  model: "qwen3:4b-instruct-2507-q4_K_M",
  language: "auto",
  onLanguage: vi.fn(),
  onPaper: vi.fn(),
  onSaved: vi.fn(),
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api).mockResolvedValue({ id: "exam-job" });
});
it("answers a separate paper, preserves per-answer citations and uses selected language", async () => {
  vi.mocked(consumeJob).mockImplementation(async (_id, receive) => {
    receive({ type: "status", message: "Question 1 of 1" });
    receive({
      type: "question",
      number: "1",
      question: "انرژی چیست؟",
      answer: "انرژی توانایی انجام کار است. [S1]",
      status: "answered",
      sources: [
        {
          id: "S1",
          pdf_id: 1,
          page: 1,
          filename: "study-fa.pdf",
          excerpt: "انرژی",
        },
      ],
    });
    receive({
      type: "done",
      metrics: { question_count: 1, failed_questions: 0, review_required: 0 },
    });
  });
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  render(<ExamRunner {...props} />);
  fireEvent.change(screen.getByLabelText("Answer language"), {
    target: { value: "fa" },
  });
  expect(props.onLanguage).toHaveBeenCalledWith("fa");
  fireEvent.click(screen.getByText("Answer this paper"));
  await screen.findByText("Question 1 · Answer ready for review");
  const request = JSON.parse(
    String(
      vi
        .mocked(api)
        .mock.calls.find(
          (call) => call[0] === "/summarizer/study/exams/jobs",
        )?.[1]?.body,
    ),
  );
  expect(request.reference_pdf_ids).toEqual([1]);
  expect(request.exam_pdf_id).toBe(2);
  expect(request.approve_calculations).toBe(false);
  fireEvent.click(
    screen.getByRole("button", { name: "Open source S1, PDF page 1" }),
  );
  expect(open).toHaveBeenCalledWith(
    "/api/summarizer/documents/1/file#page=1",
    "_blank",
    "noopener",
  );
  expect(props.onSaved).toHaveBeenCalled();
  open.mockRestore();
});
it("handles rejected exam creation and excludes the selected paper from references", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Local model unavailable"));
  render(
    <ExamRunner
      {...props}
      documents={[
        ...documents,
        { id: 2, filename: "exam-fa.pdf", status: "completed" },
      ]}
    />,
  );
  expect(screen.queryByText("exam-fa.pdf")).toBeNull();
  fireEvent.click(screen.getByText("Answer this paper"));
  await waitFor(() =>
    expect(
      screen
        .getAllByRole("alert")
        .some((el) => el.textContent?.includes("Local model unavailable")),
    ).toBe(true),
  );
});
it("uploads question papers without adding them as study evidence", async () => {
  vi.mocked(api).mockResolvedValue([
    { id: 3, filename: "paper.pdf", status: "processing" },
  ]);
  vi.mocked(waitDocuments).mockResolvedValue([
    { id: 3, filename: "paper.pdf", status: "completed" },
  ]);
  const { container } = render(<ExamRunner {...props} />);
  fireEvent.change(container.querySelector("input[type=file]")!, {
    target: {
      files: [new File(["pdf"], "paper.pdf", { type: "application/pdf" })],
    },
  });
  await waitFor(() =>
    expect(props.onPaper).toHaveBeenCalledWith(
      expect.objectContaining({ id: 3 }),
    ),
  );
  expect(screen.getByLabelText("study-fa.pdf")).toBeChecked();
});
it("normalizes common model math delimiters while preserving code and RTL prose", () => {
  expect(mathMarkdown("\\[x^2\\]")).toContain("$$\nx^2\n$$");
  expect(mathMarkdown("`\\(x\\)`")).toBe("`\\(x\\)`");
  const { container } = render(
    <Answer text={"ریشه‌ها: \\(x=2\\)"} sources={[]} onSource={() => {}} />,
  );
  expect(container.querySelector(".answer")).toHaveAttribute("dir", "auto");
  expect(container.querySelector(".katex")).not.toBeNull();
});
it("links Persian source-label variants only when the server supplied that source", () => {
  const source = {
    id: "S1",
    pdf_id: 1,
    page: 1,
    filename: "study-fa.pdf",
    excerpt: "انرژی",
  };
  render(
    <Answer
      text={"پاسخ [ س ۱ ] و ناشناخته [س۹۹]"}
      sources={[source]}
      onSource={() => {}}
    />,
  );
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(screen.getByRole("button")).toHaveAccessibleName(
    "Open source S1, PDF page 1",
  );
});
it("shows pending calculator inputs and opens them for explicit review", async () => {
  const input = {
    operation: "solve",
    expression: "x^2=4",
    variable: "x",
    domain: "real",
  };
  vi.mocked(consumeJob).mockImplementation(async (_id, receive) => {
    receive({
      type: "question",
      number: "1",
      question: "حل کنید",
      answer: "ابتدا معادله را بررسی کنید.",
      status: "needs_review",
      sources: [],
      metrics: { interpretation: { math: input } },
    });
    receive({
      type: "done",
      metrics: { question_count: 1, review_required: 1 },
    });
  });
  const review = vi.fn();
  const { container } = render(<ExamRunner {...props} onReview={review} />);
  fireEvent.click(screen.getByText("Answer this paper"));
  await screen.findByText("Review in solver");
  await waitFor(() =>
    expect(screen.getByText("Review in solver")).toBeEnabled(),
  );
  expect(container.querySelector(".katex")).not.toBeNull();
  fireEvent.click(screen.getByText("Review in solver"));
  expect(review).toHaveBeenCalledWith("حل کنید", input);
});

it("explains the reference limit and allows deselection to recover", async () => {
  render(
    <ExamRunner
      {...props}
      documents={[1, 3, 4, 5].map((id) => ({
        id,
        filename: `source-${id}.pdf`,
        status: "completed",
      }))}
    />,
  );
  expect(
    screen.getByText(/Choose 1–3 source PDFs. 3 selected/),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("source-5.pdf")).not.toBeChecked();
  fireEvent.click(screen.getByLabelText("source-5.pdf"));
  expect(screen.getByRole("alert")).toHaveTextContent("Uncheck a reference");
  expect(screen.getByText("Answer this paper")).toBeDisabled();
  fireEvent.click(screen.getByLabelText("source-1.pdf"));
  expect(screen.getByText("Answer this paper")).toBeEnabled();
});

it("opens the offending long question from the blocked submission and recovers after correction", async () => {
  vi.mocked(api).mockImplementation(async (path) =>
    path.includes("/papers/")
      ? {
          questions: [
            { number: "1", text: "Valid question", page: 1 },
            { number: "2", text: "Long text ".repeat(900), page: 1 },
          ],
        }
      : [],
  );
  const { container } = render(<ExamRunner {...props} />);
  await screen.findByText(/Question 2: over 8,000 characters/);
  expect(screen.getByText("Answer this paper")).toBeDisabled();
  expect(container.querySelector(".exam-question-review")).not.toHaveAttribute(
    "open",
  );
  fireEvent.click(screen.getByText("Review question 2"));
  expect(container.querySelector(".exam-question-review")).toHaveAttribute(
    "open",
  );
  expect(screen.getByLabelText("Full question text")).toHaveValue(
    "Long text ".repeat(900),
  );
  fireEvent.change(screen.getByLabelText("Full question text"), {
    target: { value: "Corrected second question" },
  });
  expect(screen.queryByText(/Question 2: over 8,000 characters/)).toBeNull();
  expect(screen.getByText("Answer this paper")).toBeEnabled();
});
