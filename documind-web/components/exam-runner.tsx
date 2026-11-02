"use client";
import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api, post, consumeJob, waitDocuments } from "../lib/api";
import type { Document, Source } from "../lib/types";
import { safeSources } from "../lib/workspaces";
import { Answer } from "./answer";
import { LanguageSelect } from "./language-select";
import { ExamReview, type ReviewedQuestion } from "./exam-review";
import { AnswerFeedback } from "./answer-feedback";
import { citedSources } from "../lib/exam-export";
import { inputMarkdown, type MathInput, type Calculation } from "../lib/study";
export type ExamAnswer = {
  number: string;
  question: string;
  answer: string;
  status: string;
  sources: Source[];
  run_id?: string;
  question_index?: number;
  metrics?: { math?: Calculation; interpretation?: { math?: MathInput } };
};
export function ExamAnswers({
  rows,
  busy = false,
  onReview,
}: {
  rows: ExamAnswer[];
  busy?: boolean;
  onReview?: (question: string, input: MathInput) => void;
}) {
  return (
    <div className="exam-answers">
      {rows.map((row, index) => {
        const inputs =
          row.metrics?.math?.input || row.metrics?.interpretation?.math;
        return (
          <article className="exam-answer" key={`${row.number}-${index}`}>
            <h3>
              Question {row.number} ·{" "}
              {row.status === "needs_review"
                ? "Review interpreted inputs"
                : row.status === "needs_information"
                  ? "More information needed"
                  : row.status === "failed"
                    ? "Failed"
                    : "Answer ready for review"}
            </h3>
            <p dir="auto">{row.question}</p>
            {inputs && (
              <details open={row.status === "needs_review"}>
                <summary>Calculator inputs to review</summary>
                <Answer
                  text={inputMarkdown(inputs)}
                  sources={[]}
                  onSource={() => {}}
                />
                {onReview && (
                  <button
                    disabled={busy}
                    onClick={() => onReview(row.question, inputs)}
                  >
                    Review in solver
                  </button>
                )}
              </details>
            )}
            <Answer
              text={row.answer}
              sources={row.sources}
              onSource={(source) =>
                window.open(
                  `/api/summarizer/documents/${source.pdf_id}/file#page=${source.page}`,
                  "_blank",
                  "noopener",
                )
              }
            />
            {row.sources.length > 0 &&
              citedSources(row.answer, row.sources).length === 0 && (
                <details>
                  <summary>
                    Retrieved pages for review (no inline citations)
                  </summary>
                  {row.sources.map((s) => (
                    <p key={s.id}>
                      <a
                        href={`/api/summarizer/documents/${s.pdf_id}/view?page=${s.page}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.filename} · p. {s.page}
                      </a>
                    </p>
                  ))}
                </details>
              )}
            {row.metrics?.math && (
              <details className="exam-checks">
                <summary>Calculation checks & assumptions</summary>
                <p>
                  {row.metrics.math.verified
                    ? "Listed checks passed on these inputs."
                    : "This result is not independently verified."}
                </p>
                <ul>
                  {row.metrics.math.checks.map((c, i) => (
                    <li key={i}>
                      {c.label}: {c.passed ? "passed" : "not verified"}
                    </li>
                  ))}
                </ul>
                <p>{row.metrics.math.assumptions?.join(" ")}</p>
              </details>
            )}
            {row.run_id !== undefined && row.question_index !== undefined && (
              <AnswerFeedback
                run={row.run_id}
                index={row.question_index}
                disabled={busy}
              />
            )}
          </article>
        );
      })}
    </div>
  );
}
export function ExamRunner({
  workspaceId,
  paper,
  documents,
  model,
  language,
  onLanguage,
  onPaper,
  onSaved,
  onBusy,
  onReview,
  answers,
  onAnswers,
  onViewResults,
}: {
  workspaceId: string;
  paper: number;
  documents: Document[];
  model: string;
  language: string;
  onLanguage: (v: string) => void;
  onPaper: (d: Document) => void;
  onSaved: () => void;
  onBusy?: (value: boolean) => void;
  onReview?: (question: string, input: MathInput) => void;
  answers?: ExamAnswer[];
  onAnswers?: Dispatch<SetStateAction<ExamAnswer[]>>;
  onViewResults?: () => void;
}) {
  const [references, setReferences] = useState<number[]>([]),
    [localRows, setLocalRows] = useState<ExamAnswer[]>([]),
    [busy, setBusy] = useState(false),
    [phase, setPhase] = useState(""),
    [error, setError] = useState(""),
    [approve, setApprove] = useState(false);
  const [style, setStyle] = useState("direct"),
    [questions, setQuestions] = useState<ReviewedQuestion[] | undefined>(),
    [runId, setRunId] = useState(""),
    [history, setHistory] = useState<
      { id: string; state: string; completed: number; exam_pdf_id: number }[]
    >([]),
    [resumeId, setResumeId] = useState("");
  const [reviewTarget, setReviewTarget] = useState<
    { index: number; request: number } | undefined
  >();
  const currentRun = useRef("");
  useEffect(() => {
    api<unknown>(
      `/summarizer/study/exams/runs?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
      .then((v) => {
        if (Array.isArray(v)) setHistory(v);
      })
      .catch(() => {});
  }, [workspaceId, busy]);
  const rows = answers ?? localRows,
    setRows = onAnswers ?? setLocalRows;
  const input = useRef<HTMLInputElement>(null),
    controller = useRef<AbortController | null>(null),
    job = useRef<string | null>(null);
  const eligible = documents.filter((d) => d.id !== paper);
  useEffect(() => {
    setReferences(
      documents
        .filter((d) => d.id !== paper)
        .slice(0, 3)
        .map((d) => d.id),
    );
    setReviewTarget(undefined);
    setRows([]);
  }, [paper, documents.map((d) => d.id).join(",")]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    onBusy?.(busy);
    return () => onBusy?.(false);
  }, [busy, onBusy]);
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    const abort = new AbortController();
    controller.current = abort;
    try {
      const form = new FormData();
      form.append("files", file);
      const saved = await api<Document[]>("/summarizer/upload", {
        method: "POST",
        body: form,
        signal: abort.signal,
      });
      const ready = await waitDocuments(
        saved.map((d) => d.id),
        () => setPhase("Reading the question paper"),
        abort.signal,
      );
      onPaper(ready[0]);
      setPhase("Question paper ready. Choose its study references.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Question paper upload failed");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }
  async function run(resume?: Record<string, unknown>) {
    setBusy(true);
    setError("");
    setRows([]);
    setPhase("Preparing the exam");
    const abort = new AbortController();
    controller.current = abort;
    try {
      const created = await api<{ id: string; run_id?: string }>(
        "/summarizer/study/exams/jobs",
        post({
          workspace_id: workspaceId,
          exam_pdf_id: paper,
          reference_pdf_ids: references,
          model,
          answer_language: language,
          approve_calculations: approve,
          answer_style: style,
          ...(questions !== undefined ? { questions } : {}),
          ...resume,
        }),
      );
      job.current = created.id;
      currentRun.current = created.run_id || "";
      setRunId(currentRun.current);
      await consumeJob(
        created.id,
        (event) => {
          if (event.type === "status") setPhase(event.message || "Working");
          if (event.type === "metadata" && typeof event.run_id === "string") {
            currentRun.current = event.run_id;
            setRunId(event.run_id);
          }
          if (event.type === "question")
            setRows((current) => [
              ...current,
              {
                number: String(event.number),
                question: String(event.question),
                answer: String(event.answer),
                status: String(event.status),
                sources: safeSources(event.sources),
                metrics: event.metrics as ExamAnswer["metrics"],
                run_id: currentRun.current || undefined,
                question_index:
                  typeof event.question_index === "number"
                    ? event.question_index
                    : undefined,
              },
            ]);
          if (event.type === "error")
            throw new Error(event.message || "Exam task failed");
          if (event.type === "cancelled")
            setPhase(
              "Stopped. Completed question answers remain in Study library.",
            );
          if (event.type === "done")
            setPhase(
              `${event.metrics?.question_count || 0} questions processed · ${event.metrics?.failed_questions || 0} failed · ${event.metrics?.review_required || 0} need review or more information`,
            );
        },
        abort.signal,
      );
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Exam task failed");
    } finally {
      setBusy(false);
      job.current = null;
    }
  }
  async function stop() {
    try {
      if (job.current)
        await api(`/summarizer/jobs/${job.current}`, { method: "DELETE" });
      setPhase("Stopped. Completed answers are saved in Study library.");
    } catch {
      setError(
        "Could not confirm server cancellation. Completed answers remain saved; check local services.",
      );
    } finally {
      controller.current?.abort();
      setBusy(false);
    }
  }
  const invalidIndex =
    questions?.findIndex(
      (q) =>
        !q.text.trim() ||
        q.text.length > 8000 ||
        !q.number.trim() ||
        q.number.length > 30 ||
        !Number.isInteger(q.page) ||
        q.page < 1,
    ) ?? -1;
  const invalidQuestion =
    invalidIndex >= 0 ? questions?.[invalidIndex] : undefined;
  const questionProblem = invalidQuestion
    ? `Question ${invalidQuestion.number.trim() || invalidIndex + 1}: ${invalidQuestion.text.length > 8000 ? "over 8,000 characters. Split it before answering; the full text is retained." : !invalidQuestion.text.trim() ? "question text is empty. Add its text or remove the question." : !invalidQuestion.number.trim() || invalidQuestion.number.length > 30 ? "use a question number of 1–30 characters." : "choose a whole-number PDF page of at least 1."}`
    : questions?.length === 0
      ? "No questions remain. Add at least one question before answering."
      : questions && questions.length > 100
        ? "More than 100 questions are selected. Remove questions or split this paper into separate runs."
        : "";
  return (
    <section className="exam-runner" aria-label="Answer a question paper">
      <h3>Study files → question paper → answers</h3>
      <p className="study-muted">
        The question paper is separate from the evidence. Each answer keeps its
        own source pages. All readable source pages are indexed, including books
        over 100 pages. Up to 100 reviewed questions per run.
      </p>
      <button disabled={busy} onClick={() => input.current?.click()}>
        Upload question paper
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => upload(e.target.files?.[0])}
      />
      <fieldset disabled={busy} aria-describedby="exam-reference-guidance">
        <legend>Study references</legend>
        <p id="exam-reference-guidance" className="study-muted">
          Choose 1–3 source PDFs. {references.length} selected.
          {eligible.length > 3
            ? " The first three are selected initially; change them below."
            : ""}
        </p>
        {eligible.length ? (
          eligible.map((d) => (
            <label className="study-checkbox" key={d.id}>
              <input
                type="checkbox"
                checked={references.includes(d.id)}
                onChange={(e) =>
                  setReferences(
                    e.target.checked
                      ? [...references, d.id]
                      : references.filter((id) => id !== d.id),
                  )
                }
              />
              {d.filename}
              {d.page_count ? ` · ${d.page_count} pages` : ""}
            </label>
          ))
        ) : (
          <p>Add study PDFs to this workspace first.</p>
        )}
      </fieldset>
      {references.length > 3 && (
        <p role="alert">
          Select up to 3 source PDFs. Uncheck a reference before answering this
          paper.
        </p>
      )}
      <LanguageSelect value={language} onChange={onLanguage} disabled={busy} />
      <label>
        Answer format
        <select
          value={style}
          disabled={busy}
          onChange={(e) => setStyle(e.target.value)}
        >
          <option value="direct">Direct answers</option>
          <option value="worked">Answers with worked explanation</option>
        </select>
      </label>
      <ExamReview
        paper={paper}
        busy={busy}
        onQuestions={setQuestions}
        reviewTarget={reviewTarget}
      />
      <label className="study-checkbox">
        <input
          type="checkbox"
          checked={approve}
          disabled={busy}
          onChange={(e) => setApprove(e.target.checked)}
        />
        Calculate model-interpreted mathematics automatically. I will review the
        displayed inputs and checks.
      </label>
      <p className="study-muted">
        Keep this unchecked to review interpreted equations before calculation.
        Answers and marking are not guaranteed correct.
      </p>
      <div className="study-actions">
        <button
          className="primary"
          disabled={
            busy ||
            !paper ||
            !references.length ||
            references.length > 3 ||
            !!questionProblem
          }
          onClick={() => run()}
        >
          Answer this paper
        </button>
        {busy && <button onClick={stop}>Stop exam task</button>}
      </div>
      {questionProblem && (
        <div role="alert">
          <p>{questionProblem}</p>
          <button
            disabled={busy}
            onClick={() =>
              setReviewTarget({
                index: Math.max(0, invalidIndex),
                request: (reviewTarget?.request ?? 0) + 1,
              })
            }
          >
            {invalidQuestion
              ? `Review question ${invalidQuestion.number.trim() || invalidIndex + 1}`
              : "Open question editor"}
          </button>
        </div>
      )}
      {phase && <p role="status">{phase}</p>}
      {error && <p role="alert">{error}</p>}
      {runId && (
        <a
          href={`/study/print?run=${encodeURIComponent(runId)}`}
          target="_blank"
          rel="noreferrer"
        >
          Print / save answers as PDF
        </a>
      )}
      {history.filter((h) => h.exam_pdf_id === paper).length > 0 && (
        <details>
          <summary>Saved runs & recovery</summary>
          <label>
            Run
            <select
              value={resumeId}
              disabled={busy}
              onChange={(e) => setResumeId(e.target.value)}
            >
              <option value="">Choose a saved run</option>
              {history
                .filter((h) => h.exam_pdf_id === paper)
                .map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.state} · {h.completed} responses · {h.id.slice(0, 8)}
                  </option>
                ))}
            </select>
          </label>
          <button
            disabled={busy || !resumeId}
            onClick={async () => {
              try {
                const saved = await api<{ request: Record<string, unknown> }>(
                  `/summarizer/study/exams/runs/${resumeId}`,
                );
                await run({ ...saved.request, run_id: resumeId });
              } catch (e) {
                setError(e instanceof Error ? e.message : "Could not resume.");
              }
            }}
          >
            Resume saved run
          </button>
          <p className="study-muted">
            Completed responses are reused. Failed questions are retried.
            Original sources and settings are retained.
          </p>
        </details>
      )}
      {answers === undefined ? (
        <ExamAnswers rows={rows} busy={busy} onReview={onReview} />
      ) : (
        rows.length > 0 && <button onClick={onViewResults}>View answers</button>
      )}
    </section>
  );
}
