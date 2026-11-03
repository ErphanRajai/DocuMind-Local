"use client";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, post } from "../lib/api";

type Model = {
  name: string;
  description: string;
  installed: boolean;
  pending_restart?: boolean;
};
type Preview = {
  id: string;
  model: string;
  directory: string;
  model_bytes: number;
  download_bytes: number;
  copy_bytes: number;
  free_bytes: number;
  restart_required: boolean;
};
type InstallJob = Preview & {
  state: string;
  message: string;
  completed: number;
  total: number;
};
type Catalogue = {
  models: Model[];
  directory: string;
  ollama_available: boolean;
  download_available: boolean;
  windows_console: boolean;
  latest_job?: InstallJob | null;
};
const done = (job: InstallJob) =>
  ["completed", "failed", "cancelled"].includes(job.state);
const gib = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(2)} GiB`;

export function ModelLibrary({
  model,
  installed,
  recommended = [],
  disabled = false,
  onSelect,
  onInstalled,
}: {
  model: string;
  installed: string[];
  recommended?: string[];
  disabled?: boolean;
  onSelect: (name: string) => void;
  onInstalled: (names: string[]) => void;
}) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [candidate, setCandidate] = useState(model);
  const [folder, setFolder] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [job, setJob] = useState<InstallJob | null>(null);
  const [checking, setChecking] = useState(false),
    [starting, setStarting] = useState(false);
  const [error, setError] = useState(""),
    [serviceError, setServiceError] = useState("");
  const lastCompleted = useRef("");
  const folderHint = useId();
  const refresh = useCallback(async () => {
    try {
      const value = await api<Catalogue>("/local-models/catalog");
      if (!Array.isArray(value.models) || typeof value.directory !== "string")
        throw new Error(
          "The model installer returned an invalid model list. Restart DocuMind.",
        );
      setCatalogue(value);
      if (value.ollama_available)
        onInstalled(
          value.models.filter((row) => row.installed).map((row) => row.name),
        );
      setFolder((current) => current || value.directory);
      setServiceError("");
      if (value.latest_job) setJob(value.latest_job);
    } catch (e) {
      setServiceError(
        e instanceof Error ? e.message : "Model installer unavailable",
      );
    }
  }, [onInstalled]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!job || done(job)) return;
    let stopped = false;
    const timer = setInterval(async () => {
      try {
        const value = await api<InstallJob>(`/local-models/jobs/${job.id}`);
        if (!stopped) setJob(value);
      } catch (e) {
        if (!stopped)
          setError(
            e instanceof Error
              ? e.message
              : "Progress unavailable; check Command Prompt.",
          );
      }
    }, 1000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [job?.id, job?.state]);
  useEffect(() => {
    if (!job || job.state !== "completed" || lastCompleted.current === job.id)
      return;
    lastCompleted.current = job.id;
    refresh();
    if (!job.restart_required)
      api<{ installed: string[] }>("/summarizer/models")
        .then((value) => {
          if (Array.isArray(value.installed)) onInstalled(value.installed);
        })
        .catch(() =>
          setError(
            "Installed, but refreshing the answer-model list failed. Reopen settings to retry.",
          ),
        );
  }, [job, refresh, onInstalled]);
  const rows: Model[] =
    catalogue?.models ??
    [...new Set([...installed, ...recommended])].map((name) => ({
      name,
      description: "",
      installed: installed.includes(name),
    }));
  const selected = rows.find((r) => r.name === candidate);
  const running = !!job && !done(job);
  async function review(name = candidate) {
    setChecking(true);
    setError("");
    setPreview(null);
    try {
      setPreview(
        await api<Preview>(
          "/local-models/preview",
          post({ model: name, directory: folder }),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not review download.");
    } finally {
      setChecking(false);
    }
  }
  async function install() {
    if (!preview) return;
    setStarting(true);
    setError("");
    try {
      setJob(
        await api<InstallJob>(
          "/local-models/install",
          post({ preview_id: preview.id }),
        ),
      );
      setPreview(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Command Prompt could not open.",
      );
      setPreview(null);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="model-library">
      <label>
        Model library
        <select
          value={candidate}
          disabled={disabled || running || starting || checking}
          onChange={(e) => {
            const name = e.target.value;
            setCandidate(name);
            setPreview(null);
            setError("");
            if (rows.find((r) => r.name === name)?.installed) onSelect(name);
            else if (
              catalogue &&
              folder &&
              catalogue.ollama_available &&
              catalogue.windows_console
            )
              void review(name);
          }}
        >
          {!rows.some((r) => r.name === candidate) && (
            <option value={candidate}>{candidate} — Not installed</option>
          )}
          {rows.map((row) => (
            <option key={row.name} value={row.name}>
              {row.name} —{" "}
              {catalogue && !catalogue.ollama_available
                ? "Status unavailable"
                : row.pending_restart
                  ? "Installed — restart DocuMind"
                  : row.installed
                    ? "Installed"
                    : "Not installed"}
            </option>
          ))}
        </select>
      </label>
      <p className="model-description">
        {selected?.description}{" "}
        {selected?.installed
          ? "Installed locally."
          : catalogue && !catalogue.ollama_available
            ? "Installed status is unavailable; your answer model is unchanged."
            : "Not installed; your current answer model is unchanged."}
      </p>
      <p className="model-description">
        Answer model: <span dir="ltr">{model}</span>
      </p>
      {catalogue && (
        <button disabled={running || starting || checking} onClick={refresh}>
          Refresh models
        </button>
      )}
      {serviceError && (
        <p role="status" className="model-description">
          {serviceError}{" "}
          <button onClick={refresh}>Retry installer connection</button>
        </p>
      )}
      {catalogue && (
        <>
          {!catalogue.windows_console && (
            <p className="model-description">
              The visible Command Prompt installer requires Windows. Use the
              DocuMind CLI on this platform.
            </p>
          )}
          {!catalogue.ollama_available && (
            <p role="alert">
              Ollama is unavailable, so installed status cannot be confirmed.
              Start Ollama and refresh.
            </p>
          )}
          <label>
            Model library folder
            <input
              aria-label="Model library folder"
              aria-describedby={folderHint}
              value={folder}
              spellCheck={false}
              autoComplete="off"
              disabled={running || starting || checking || disabled}
              onChange={(e) => {
                setFolder(e.target.value);
                setPreview(null);
                setError("");
              }}
            />
            <small id={folderHint}>
              Use an absolute local folder. Changing it copies the existing
              library and requires a DocuMind restart. Original files stay in
              place.
            </small>
          </label>
          <button
            disabled={
              disabled ||
              running ||
              starting ||
              checking ||
              !folder ||
              !catalogue.windows_console ||
              !catalogue.ollama_available ||
              selected?.description === "Installed locally"
            }
            onClick={() => review()}
          >
            {checking
              ? "Checking size and free space…"
              : "Review download size & folder"}
          </button>
          {preview && (
            <section
              className="model-install-review"
              aria-label="Review model installation"
            >
              <h3>Review installation</h3>
              <p className="model-destination" dir="ltr">{preview.model}</p>
              <dl>
                <div>
                  <dt>Model files</dt>
                  <dd>{gib(preview.model_bytes)}</dd>
                </div>
                <div>
                  <dt>Download up to</dt>
                  <dd>{gib(preview.download_bytes)}</dd>
                </div>
                <div>
                  <dt>Free space</dt>
                  <dd>{gib(preview.free_bytes)}</dd>
                </div>
                {preview.restart_required && (
                  <div>
                    <dt>Existing library copy</dt>
                    <dd>{gib(preview.copy_bytes)}</dd>
                  </div>
                )}
              </dl>
              <p className="model-destination" dir="ltr">
                {preview.directory}
              </p>
              <p className="model-description">
                File sizes are not a RAM/VRAM requirement. Downloading needs
                internet; using an installed model stays local.
              </p>
              {preview.restart_required && (
                <p>
                  Restart DocuMind after installation to activate this folder.
                  Existing models are preserved.
                </p>
              )}
              <button
                className="primary"
                disabled={
                  disabled ||
                  starting ||
                  running ||
                  (preview.restart_required && !catalogue.download_available)
                }
                onClick={install}
              >
                {starting
                  ? "Opening Command Prompt…"
                  : "Install in Command Prompt"}
              </button>
              {preview.restart_required && !catalogue.download_available && (
                <p role="alert">
                  Ollama's Windows executable is missing. Run
                  Install_DocuMind.cmd before using another folder.
                </p>
              )}
            </section>
          )}
        </>
      )}
      {job && (
        <section
          className="model-install-progress"
          aria-label="Model installation progress"
        >
          <p className="model-destination" dir="ltr">{job.model}</p>
          <p role="status">{job.message}</p>
          {running && (
            <>
              <progress
                aria-label="Current model file download"
                max={job.total || undefined}
                value={
                  job.total ? Math.min(job.completed, job.total) : undefined
                }
              />
              {job.total > 0 && (
                <p className="model-description">
                  Current file: {gib(job.completed)} / {gib(job.total)}
                </p>
              )}
              <p className="model-description">
                Keep DocuMind open. You can close these settings and reopen them
                to check progress.
              </p>
              <button
                onClick={async () => {
                  try {
                    setJob(
                      await api<InstallJob>(
                        `/local-models/jobs/${job.id}/cancel`,
                        post({}),
                      ),
                    );
                  } catch {
                    setError(
                      "Could not confirm cancellation. Press Ctrl+C in the installation window.",
                    );
                  }
                }}
              >
                Cancel installation
              </button>
            </>
          )}
          {job.state === "completed" &&
            !job.restart_required &&
            installed.includes(job.model) && (
              <button disabled={disabled} onClick={() => onSelect(job.model)}>
                Use installed model
              </button>
            )}
          {["failed", "cancelled"].includes(job.state) && (
            <p>
              Review the download again to retry. Ollama resumes downloaded
              parts.
            </p>
          )}
        </section>
      )}
      {error && <p role="alert">{error}</p>}
      <p className="model-description">
        Command-line help: <code>documind --help</code> from the DocuMind
        folder.
      </p>
    </div>
  );
}
