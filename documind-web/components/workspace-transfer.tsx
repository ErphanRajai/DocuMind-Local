"use client";
import { useRef, useState } from "react";
import { api } from "../lib/api";
export function WorkspaceTransfer({
  workspace,
  disabled = false,
}: {
  workspace: string;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <div className="workspace-transfer">
      <a
        aria-disabled={disabled || busy}
        href={
          disabled || busy
            ? undefined
            : `/api/summarizer/workspaces/${encodeURIComponent(workspace)}/archive`
        }
      >
        Download complete workspace ZIP
      </a>
      <button
        disabled={disabled || busy}
        onClick={() => input.current?.click()}
      >
        Restore workspace ZIP
      </button>
      <span className="study-muted">
        Includes original PDFs and saved answers. Keep this private backup safe.
      </span>
      <input
        ref={input}
        type="file"
        accept=".zip"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setBusy(true);
          setError("");
          try {
            const form = new FormData();
            form.append("archive", file);
            const result = await api<{ workspace_id: string }>(
              "/summarizer/workspaces/restore",
              { method: "POST", body: form },
            );
            location.assign(
              `/study?workspace=${encodeURIComponent(result.workspace_id)}`,
            );
          } catch (reason) {
            setError(
              reason instanceof Error
                ? reason.message
                : "Restore failed. Existing work is retained.",
            );
          } finally {
            setBusy(false);
            if (input.current) input.current.value = "";
          }
        }}
      />
      {busy && <p role="status">Validating and restoring the archive…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
