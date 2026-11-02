"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
export type ReviewedQuestion = {
  number: string;
  text: string;
  page: number;
  warnings?: string[];
};
export function ExamReview({
  paper,
  busy,
  onQuestions,
  reviewTarget,
}: {
  paper: number;
  busy: boolean;
  onQuestions: (q: ReviewedQuestion[] | undefined) => void;
  reviewTarget?: { index: number; request: number };
}) {
  const [rows, setRows] = useState<ReviewedQuestion[]>([]),
    [selected, setSelected] = useState(0),
    [error, setError] = useState("");
  const disclosure = useRef<HTMLDetailsElement>(null),
    editor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!reviewTarget) return;
    setSelected(reviewTarget.index);
    if (disclosure.current) disclosure.current.open = true;
    editor.current?.focus();
    disclosure.current?.scrollIntoView?.({ block: "center" });
  }, [reviewTarget]);
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    setSelected(0);
    setError("");
    onQuestions(undefined);
    if (paper)
      api<{ questions: ReviewedQuestion[] }>(
        `/summarizer/study/papers/${paper}`,
        { signal: controller.signal },
      )
        .then((value) => {
          if (Array.isArray(value.questions)) {
            const q = value.questions.map(
              ({ number, text, page, warnings }) => ({
                number,
                text,
                page,
                warnings,
              }),
            );
            setRows(q);
            onQuestions(q);
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        });
    return () => controller.abort();
  }, [paper, onQuestions]);
  function update(next: ReviewedQuestion[]) {
    setRows(next);
    onQuestions(next);
  }
  const row = rows[selected];
  if (!paper) return null;
  return (
    <details ref={disclosure} className="exam-question-review">
      <summary>Review or correct questions ({rows.length})</summary>
      <p className="study-muted">
        The original page stays beside the extracted text. Check symbols,
        choices, subquestions and figure data. Changes here apply to this run.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Question to review
        <select
          disabled={busy}
          value={selected}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {rows.map((q, i) => (
            <option key={i} value={i}>
              {q.number} · p. {q.page}
            </option>
          ))}
        </select>
      </label>
      {row && (
        <div className="exam-review-grid">
          <div>
            <label>
              Full question text
              <textarea
                ref={editor}
                dir="auto"
                disabled={busy}
                rows={10}
                value={row.text}
                onChange={(e) =>
                  update(
                    rows.map((q, i) =>
                      i === selected ? { ...q, text: e.target.value } : q,
                    ),
                  )
                }
              />
            </label>
            <label>
              Question number
              <input
                disabled={busy}
                value={row.number}
                maxLength={30}
                onChange={(e) =>
                  update(
                    rows.map((q, i) =>
                      i === selected ? { ...q, number: e.target.value } : q,
                    ),
                  )
                }
              />
            </label>
            <label>
              Original PDF page
              <input
                type="number"
                min={1}
                disabled={busy}
                value={row.page}
                onChange={(e) =>
                  update(
                    rows.map((q, i) =>
                      i === selected
                        ? { ...q, page: Number(e.target.value) }
                        : q,
                    ),
                  )
                }
              />
            </label>
            <p className={row.text.length > 8000 ? "warning" : "study-muted"}>
              {row.text.length.toLocaleString()} / 8,000 characters. Longer
              questions must be split; their text is retained.
            </p>
            {row.warnings?.map((w) => (
              <p className="warning" key={w}>
                {w}
              </p>
            ))}
          </div>
          <div>
            <a
              href={`/api/summarizer/documents/${paper}/view?page=${row.page}`}
              target="_blank"
              rel="noreferrer"
            >
              Open original page at full size
            </a>
            <img
              src={`/api/summarizer/documents/${paper}/pages/${row.page}.png`}
              alt={`Original exam page ${row.page}`}
              loading="lazy"
            />
          </div>
        </div>
      )}
      <div className="study-actions">
        <button
          disabled={busy || rows.length >= 100}
          onClick={() => {
            update([
              ...rows,
              {
                number: String(rows.length + 1),
                text: "",
                page: row?.page || 1,
              },
            ]);
            setSelected(rows.length);
          }}
        >
          Add question / subquestion
        </button>
        <button
          disabled={busy || !row}
          onClick={() => {
            update(rows.filter((_, i) => i !== selected));
            setSelected(0);
          }}
        >
          Remove selected question
        </button>
      </div>
    </details>
  );
}
