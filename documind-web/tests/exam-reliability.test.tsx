import { it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExamReview } from "../components/exam-review";
import { AnswerFeedback } from "../components/answer-feedback";
import { api } from "../lib/api";
import { citedSources } from "../lib/exam-export";
import { Answer } from "../components/answer";
vi.mock("../lib/api", () => ({
  api: vi.fn(),
  post: (value: unknown) => ({ method: "POST", body: JSON.stringify(value) }),
}));
beforeEach(() => vi.clearAllMocks());
it("distinguishes cited pages from available retrieval and isolates complete identifiers", () => {
  const sources = [
    { id: "S1", pdf_id: 1, page: 119, filename: "source.pdf", excerpt: "code" },
    {
      id: "S2",
      pdf_id: 1,
      page: 120,
      filename: "source.pdf",
      excerpt: "other",
    },
  ];
  expect(
    citedSources("پاسخ [ س ۱ ] و مثال `[S2]`", sources).map((s) => s.id),
  ).toEqual(["S1"]);
  const { container } = render(
    <Answer
      text="کد REF-AB01234567 است. [S1]"
      sources={sources}
      onSource={() => {}}
    />,
  );
  expect(container.querySelector("code")?.textContent).toBe("REF-AB01234567");
});
it("preserves long questions for correction and links the original page", async () => {
  const text = "Long question ".repeat(800),
    receive = vi.fn();
  vi.mocked(api).mockResolvedValue({
    questions: [
      { number: "1", text, page: 112, warnings: ["Review equation symbols"] },
    ],
  });
  render(<ExamReview paper={2} busy={false} onQuestions={receive} />);
  await screen.findByText(/Review or correct questions \(1\)/);
  fireEvent.click(screen.getByText(/Review or correct questions/));
  expect(screen.getByLabelText("Full question text")).toHaveValue(text);
  expect(
    screen.getByRole("link", { name: "Open original page at full size" }),
  ).toHaveAttribute("href", "/api/summarizer/documents/2/view?page=112");
  fireEvent.change(screen.getByLabelText("Full question text"), {
    target: { value: "Corrected equation: x^2=4" },
  });
  expect(receive).toHaveBeenLastCalledWith([
    {
      number: "1",
      text: "Corrected equation: x^2=4",
      page: 112,
      warnings: ["Review equation symbols"],
    },
  ]);
});
it("stores correction feedback separately and reports a save failure for retry", async () => {
  vi.mocked(api)
    .mockRejectedValueOnce(new Error("Service unavailable"))
    .mockResolvedValueOnce({ id: "saved" });
  render(<AnswerFeedback run={"a".repeat(32)} index={3} />);
  fireEvent.click(screen.getByText("Report or correct this answer"));
  fireEvent.change(screen.getByLabelText("Correction or note"), {
    target: { value: "The cited page describes a different formula." },
  });
  fireEvent.click(screen.getByText("Save feedback locally"));
  await screen.findByText("Service unavailable");
  fireEvent.click(screen.getByText("Save feedback locally"));
  await screen.findByText(
    "Saved locally for review. The original answer is retained.",
  );
  expect(
    JSON.parse(String(vi.mocked(api).mock.calls[1][1]?.body)).question_index,
  ).toBe(3);
});
