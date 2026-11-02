"use client";
import { useState } from "react";
import { api, post } from "../lib/api";
export function AnswerFeedback({
  run,
  index,
  disabled = false,
}: {
  run: string;
  index: number;
  disabled?: boolean;
}) {
  const [reason, setReason] = useState("interpretation"),
    [text, setText] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <details className="answer-feedback">
      <summary>Report or correct this answer</summary>
      <label>
        Issue
        <select
          disabled={busy || disabled}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        >
          {[
            "interpretation",
            "calculation",
            "citation",
            "missing_information",
            "other",
          ].map((r) => (
            <option key={r} value={r}>
              {r.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
      <label>
        Correction or note
        <textarea
          dir="auto"
          maxLength={2000}
          disabled={busy || disabled}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
        />
      </label>
      <button
        disabled={busy || disabled}
        onClick={async () => {
          setBusy(true);
          try {
            await api(
              `/summarizer/study/exams/runs/${run}/feedback`,
              post({ question_index: index, reason, correction: text }),
            );
            setMessage(
              "Saved locally for review. The original answer is retained.",
            );
          } catch (e) {
            setMessage(
              e instanceof Error ? e.message : "Could not save; retry.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        Save feedback locally
      </button>
      <p role="status">{message}</p>
    </details>
  );
}
