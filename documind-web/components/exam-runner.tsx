"use client";
import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api, post, consumeJob, waitDocuments } from "../lib/api";
import type { Document, Source } from "../lib/types";
import { safeSources } from "../lib/workspaces";
import { Answer } from "./answer";
import { LanguageSelect } from "./language-select";
import { inputMarkdown, type MathInput, type Calculation } from "../lib/study";
export type ExamAnswer = {
  number: string;
  question: string;
  answer: string;
  status: string;
  sources: Source[];
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
  const rows = answers ?? localRows,
    setRows = onAnswers ?? setLocalRows;
  const input = useRef<HTMLInputElement>(null),
    controller = useRef<AbortController | null>(null),
    job = useRef<string | null>(null);
  const eligible = documents.filter((d) => d.id !== paper);
  useEffect(() => {
    setReferences(documents.filter((d) => d.id !== paper).map((d) => d.id));
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
  async function run() {
    setBusy(true);
    setError("");
    setRows([]);
    setPhase("Preparing the exam");
    const abort = new AbortController();
    controller.current = abort;
    try {
      const created = await api<{ id: string }>(
        "/summarizer/study/exams/jobs",
        post({
          workspace_id: workspaceId,
          exam_pdf_id: paper,
          reference_pdf_ids: references,
          model,
          answer_language: language,
          approve_calculations: approve,
        }),
      );
      job.current = created.id;
      await consumeJob(
        created.id,
        (event) => {
          if (event.type === "status") setPhase(event.message || "Working");
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
  return (
    <section className="exam-runner" aria-label="Answer a question paper">
      <h3>Study files → question paper → answers</h3>
      <p className="study-muted">
        The question paper is separate from the evidence. Each answer keeps its
        own source pages. Up to 20 numbered questions per run.
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
      <fieldset disabled={busy}>
        <legend>Study references</legend>
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
            </label>
          ))
        ) : (
          <p>Add study PDFs to this workspace first.</p>
        )}
      </fieldset>
      <LanguageSelect value={language} onChange={onLanguage} disabled={busy} />
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
            busy || !paper || !references.length || references.length > 3
          }
          onClick={run}
        >
          Answer this paper
        </button>
        {busy && <button onClick={stop}>Stop exam task</button>}
      </div>
      {phase && <p role="status">{phase}</p>}
      {error && <p role="alert">{error}</p>}
      {answers === undefined ? (
        <ExamAnswers rows={rows} busy={busy} onReview={onReview} />
      ) : (
        rows.length > 0 && <button onClick={onViewResults}>View answers</button>
      )}
    </section>
  );
}
