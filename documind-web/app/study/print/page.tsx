"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { citedSources } from "../../../lib/exam-export";
import { Answer } from "../../../components/answer";
import type { ExamAnswer } from "../../../components/exam-runner";
export default function PrintAnswers() {
  const [rows, setRows] = useState<ExamAnswer[]>([]),
    [language, setLanguage] = useState("auto"),
    [error, setError] = useState(""),
    [ready, setReady] = useState(false);
  useEffect(() => {
    const run = new URLSearchParams(location.search).get("run");
    if (!run) {
      setError("Choose an exam run first.");
      return;
    }
    api<{ answers: Record<string, ExamAnswer>; language: string }>(
      `/summarizer/study/exams/runs/${encodeURIComponent(run)}`,
    )
      .then((value) => {
        setRows(
          Object.values(value.answers).sort(
            (a, b) => (a.question_index || 0) - (b.question_index || 0),
          ),
        );
        setLanguage(value.language);
        setReady(true);
      })
      .catch((e) => setError(e.message));
  }, []);
  function label(status: string) {
    const labels: Record<string, string> =
      language === "fa"
        ? {
            answered: "پاسخ آمادهٔ بررسی",
            needs_information: "اطلاعات ناکافی",
            needs_review: "نیازمند بررسی",
            failed: "خطا",
          }
        : {
            answered: "Answer ready for review",
            needs_information: "More information needed",
            needs_review: "Review required",
            failed: "Failed",
          };
    return labels[status] || status;
  }
  return (
    <main
      className="exam-print"
      dir={language === "fa" || language === "ar" ? "rtl" : "ltr"}
      lang={language === "auto" ? "en" : language}
    >
      <div className="print-controls">
        <a href="/study">Back to exam desk</a>
        <button disabled={!ready} onClick={() => window.print()}>
          Print / save as PDF
        </button>
        <button
          disabled={!ready}
          onClick={() => {
            const body = rows
              .map(
                (r) =>
                  `## ${r.number} · ${label(r.status)}\n\n${r.question}\n\n${r.answer}\n\n` +
                  (citedSources(r.answer, r.sources).length
                    ? citedSources(r.answer, r.sources)
                    : r.sources
                  )
                    .map((s) => `${s.id}: ${s.filename}, PDF page ${s.page}`)
                    .join("\n"),
              )
              .join("\n\n");
            const url = URL.createObjectURL(
              new Blob([body], { type: "text/markdown;charset=utf-8" }),
            );
            const a = document.createElement("a");
            a.href = url;
            a.download = "exam-answers.md";
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        >
          Download Markdown
        </button>
      </div>
      <h1>{language === "fa" ? "پاسخ‌های آزمون" : "Exam answers"}</h1>
      {error && <p role="alert">{error}</p>}
      {!ready && !error && <p role="status">Loading saved responses…</p>}
      {rows.map((r, i) => (
        <article key={i}>
          <h2>
            {r.number} · {label(r.status)}
          </h2>
          <p dir="auto">{r.question}</p>
          <Answer
            text={r.answer}
            sources={r.sources}
            onSource={(s) =>
              window.open(
                `/api/summarizer/documents/${s.pdf_id}/view?page=${s.page}`,
                "_blank",
                "noopener",
              )
            }
          />
          <p>
            {citedSources(r.answer, r.sources).length
              ? language === "fa"
                ? "صفحه‌های ارجاع‌شده"
                : "Cited pages"
              : language === "fa"
                ? "صفحه‌های بازیابی‌شده برای بررسی؛ بدون ارجاع در پاسخ"
                : "Retrieved pages for review; no inline citations"}
          </p>
          <ul>
            {(citedSources(r.answer, r.sources).length
              ? citedSources(r.answer, r.sources)
              : r.sources
            ).map((s) => (
              <li dir="auto" key={s.id}>
                {s.id} · {s.filename} ·{" "}
                {language === "fa" ? "صفحهٔ" : "PDF page"} {s.page}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </main>
  );
}
