"use client";
import { useEffect, useRef, useState } from "react";
import {
  Plus,
  ArrowUp,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  BookOpen,
  FileText,
  Paperclip,
  Square,
  RotateCcw,
  Check,
  Copy,
  Search,
  SlidersHorizontal,
  X,
  Download,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";
import { Answer } from "../components/answer";
import { PDFPage } from "../components/pdf-page";
import {
  loadSavedWorkspaces,
  persistWorkspace,
  mergeWorkspaceCopies,
} from "../lib/persistence";
import { api, post, consumeJob, waitDocuments } from "../lib/api";
import {
  STORAGE_KEY,
  newWorkspace,
  restoreWorkspaces,
  historyFor,
  safeSources,
} from "../lib/workspaces";
import type {
  Workspace,
  Document,
  Message,
  Metrics,
  Source,
  JobPayload,
} from "../lib/types";

export default function Home() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]),
    [active, setActive] = useState(""),
    [loaded, setLoaded] = useState(false);
  const [question, setQuestion] = useState(""),
    [busy, setBusy] = useState(false),
    [phase, setPhase] = useState(""),
    [error, setError] = useState("");
  const [models, setModels] = useState<string[]>([]),
    [model, setModel] = useState("llama3.2:3b"),
    [length, setLength] = useState("short"),
    [health, setHealth] = useState("Checking services");
  const [settings, setSettings] = useState(false),
    [provider, setProvider] = useState("ollama"),
    [endpoint, setEndpoint] = useState(""),
    [apiKey, setApiKey] = useState("");
  const [localOnly, setLocalOnly] = useState(false);
  const [rail, setRail] = useState(true),
    [evidenceOpen, setEvidenceOpen] = useState(true),
    [mobileView, setMobileView] = useState("chat"),
    [filter, setFilter] = useState(""),
    [selected, setSelected] = useState<Source | null>(null);
  const [viewDoc, setViewDoc] = useState<Document | null>(null),
    [page, setPage] = useState(1),
    [imageError, setImageError] = useState(false),
    [copied, setCopied] = useState("");
  const [storageError, setStorageError] = useState(""),
    [progress, setProgress] = useState<{
      completed: number;
      total: number;
    } | null>(null);
  const [lastRequest, setLastRequest] = useState<{
    question?: string;
    mode?: "quick" | "complete";
  } | null>(null);
  const jobRef = useRef<string | null>(null),
    evidenceToggle = useRef<HTMLButtonElement>(null),
    evidenceTab = useRef<HTMLButtonElement>(null),
    evidenceHeading = useRef<HTMLHeadingElement>(null),
    focusEvidence = useRef(false),
    controller = useRef<AbortController | null>(null),
    filesRef = useRef<HTMLInputElement>(null),
    bottom = useRef<HTMLDivElement>(null),
    input = useRef<HTMLTextAreaElement>(null),
    scroll = useRef<HTMLDivElement>(null),
    follow = useRef(true);
  const workspace = workspaces.find((w) => w.id === active);
  const revisions = useRef<Record<string, number>>({});
  const saveQueue = useRef(Promise.resolve());
  const [remoteReady, setRemoteReady] = useState(false);
  const remoteReadyRef = useRef(remoteReady);
  remoteReadyRef.current = remoteReady;
  const recovering = useRef(false);
  const latestWorkspaces = useRef(workspaces);
  latestWorkspaces.current = workspaces;
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (window.innerWidth <= 900) setRail(false);
    let values: Workspace[] = [];
    try {
      values = restoreWorkspaces(localStorage.getItem(STORAGE_KEY));
    } catch {
      setStorageError(
        "Browser storage is unavailable. Export important conversations before closing.",
      );
    }
    const browserValues = values;
    if (!values.length) values = [newWorkspace()];
    setWorkspaces(values);
    setActive(values[0].id);
    setLoaded(true);
    loadSavedWorkspaces()
      .then((saved) => {
        revisions.current = saved.revisions;
        {
          const merged = mergeWorkspaceCopies(
            saved.values,
            browserValues,
            saved.deletedIds,
          );
          const readyValues = merged.length
            ? merged
            : [browserValues.length ? newWorkspace() : values[0]];
          setWorkspaces(readyValues);
          let pending: string | undefined;
          try {
            pending = JSON.parse(
              sessionStorage.getItem("documind.chat.job") || "null",
            )?.workspace;
          } catch {}
          setActive(
            readyValues.find((w) => w.id === pending)?.id || readyValues[0].id,
          );
        }
        setRemoteReady(true);
      })
      .catch(() => {
        setStorageError(
          "Server storage is unavailable. Your browser copy is retained; export a backup before clearing browser data.",
        );
        setRemoteReady(true);
      });
    api<{ installed: string[]; default?: string; local_only?: boolean }>(
      "/summarizer/models",
    )
      .then((v) => {
        setModels(v.installed);
        setLocalOnly(Boolean(v.local_only));
        setModel(
          v.default && v.installed.includes(v.default)
            ? v.default
            : v.installed.includes("llama3.2:3b")
              ? "llama3.2:3b"
              : v.installed[0] || "llama3.2:3b",
        );
      })
      .catch(() => setError("Could not list models. Check the local backend."));
    api<{ status: string }>("/healthz")
      .then((v) =>
        setHealth(
          v.status === "healthy"
            ? "Local services ready"
            : "A local service needs attention",
        ),
      )
      .catch(() => setHealth("Backend unavailable"));
    const leave = () => {
      controller.current?.abort();
    };
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      leave();
    };
  }, []);
  useEffect(() => {
    if (!loaded) return;
    if (saveTimer.current) return;
    saveTimer.current = setTimeout(() => {
      saveTimer.current = null;
      const snapshot = latestWorkspaces.current;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
      } catch {
        setStorageError(
          "This conversation could not be saved in browser storage. Export a copy before closing.",
        );
      }
      if (remoteReadyRef.current) {
        saveQueue.current = saveQueue.current
          .then(async () => {
            for (const w of snapshot) {
              const saved = await persistWorkspace(w, revisions.current[w.id]);
              revisions.current[w.id] = saved.revision;
              try {
                const pending = JSON.parse(
                  sessionStorage.getItem("documind.chat.job") || "null",
                );
                if (
                  pending?.workspace === w.id &&
                  w.messages.some(
                    (m) =>
                      m.id === pending.assistant && m.state !== "generating",
                  )
                )
                  sessionStorage.removeItem("documind.chat.job");
              } catch {}
            }
          })
          .catch((e) =>
            setStorageError(
              e instanceof Error
                ? e.message
                : "Server save failed. Your browser copy is retained.",
            ),
          );
      }
    }, 800);
  }, [workspaces, loaded, remoteReady]);
  useEffect(
    () => () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    },
    [],
  );
  useEffect(() => {
    if (follow.current) bottom.current?.scrollIntoView({ behavior: "instant" });
  }, [workspace?.messages, phase]);
  useEffect(() => {
    if (provider === "ollama" && model && models.includes(model))
      api("/summarizer/models/preload", post({ model })).catch(() => {});
  }, [provider, model, models]);
  useEffect(() => {
    setImageError(false);
  }, [page, viewDoc?.id]);
  function update(fn: (w: Workspace) => Workspace) {
    setWorkspaces((values) =>
      values.map((w) =>
        w.id === active ? fn({ ...w, updated: Date.now() }) : w,
      ),
    );
  }
  function append(message: Message) {
    update((w) => ({ ...w, messages: [...w.messages, message] }));
  }
  function amend(id: string, fn: (m: Message) => Message) {
    update((w) => ({
      ...w,
      messages: w.messages.map((m) => (m.id === id ? fn(m) : m)),
    }));
  }
  function create() {
    const w = newWorkspace();
    setWorkspaces((v) => [w, ...v]);
    setActive(w.id);
    setSelected(null);
    setViewDoc(null);
    setError("");
    setLastRequest(null);
    setMobileView("chat");
  }
  function choose(w: Workspace) {
    setActive(w.id);
    setSelected(null);
    setViewDoc(w.documents[0] || null);
    setPage(1);
    setError("");
    setLastRequest(null);
    setMobileView("chat");
  }
  function openSource(source: Source) {
    focusEvidence.current = true;
    if (window.innerWidth <= 900) setRail(false);
    setEvidenceOpen(true);
    setSelected(source);
    setPage(source.page);
    setViewDoc(
      workspace?.documents.find((d) => d.id === source.pdf_id) || {
        id: source.pdf_id,
        filename: source.filename,
        status: "completed",
      },
    );
    setMobileView("evidence");
  }
  function closeEvidence() {
    setEvidenceOpen(false);
    setMobileView("chat");
    (window.innerWidth <= 900 ? evidenceTab : evidenceToggle).current?.focus();
  }
  useEffect(() => {
    if (focusEvidence.current) {
      focusEvidence.current = false;
      evidenceHeading.current?.focus({ preventScroll: true });
    }
  }, [selected, mobileView, evidenceOpen]);
  useEffect(() => {
    if (!remoteReady || !workspace || recovering.current) return;
    let pending: {
      id: string;
      workspace: string;
      assistant: string;
      question: string;
      mode?: "quick" | "complete";
    } | null = null;
    try {
      pending = JSON.parse(
        sessionStorage.getItem("documind.chat.job") || "null",
      );
    } catch {}
    if (!pending || pending.workspace !== active) return;
    recovering.current = true;
    const saved = pending;
    const abort = new AbortController();
    controller.current = abort;
    jobRef.current = saved.id;
    setBusy(true);
    setPhase("Reconnecting to saved progress");
    setLastRequest(
      saved.mode ? { mode: saved.mode } : { question: saved.question },
    );
    update((w) => ({
      ...w,
      messages: w.messages.some((m) => m.id === saved.assistant)
        ? w.messages
        : [
            ...w.messages,
            ...(w.messages.at(-1)?.content === saved.question
              ? []
              : [
                  {
                    id: crypto.randomUUID(),
                    role: "user" as const,
                    content: saved.question || "Document review",
                    state: "complete" as const,
                  },
                ]),
            {
              id: saved.assistant,
              role: "assistant",
              content: "",
              state: "generating",
            },
          ],
    }));
    let text = "",
      details: Metrics = {};
    consumeJob(
      saved.id,
      (event) => {
        if (event.type === "metadata") {
          details = {
            ...details,
            ...event,
            sources: safeSources(event.sources),
          };
          amend(saved.assistant, (m) => ({ ...m, metrics: details }));
        }
        if (event.type === "text") {
          text += event.content || "";
          amend(saved.assistant, (m) => ({
            ...m,
            content: text,
            metrics: details,
          }));
        }
        if (event.type === "status") setPhase(event.message || "Reconnecting");
        if (event.type === "done") {
          details = { ...details, ...event.metrics };
          amend(saved.assistant, (m) => ({
            ...m,
            metrics: details,
            state: "complete",
          }));
          setPhase("Recovered completed answer");
        }
        if (event.type === "cancelled") {
          amend(saved.assistant, (m) => ({ ...m, state: "cancelled" }));
          setPhase("Recovered stopped draft");
        }
        if (event.type === "error")
          throw new Error(
            event.message || "Recovered incomplete draft. Retry your request.",
          );
      },
      abort.signal,
    )
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(e.message);
          amend(saved.assistant, (m) => ({ ...m, state: "failed" }));
        }
      })
      .finally(() => {
        setBusy(false);
        jobRef.current = null;
        controller.current = null;
      });
  }, [remoteReady, active]);
  async function upload(files: FileList | null) {
    if (!files?.length || !workspace) return;
    setError("");
    const incoming = Array.from(files);
    if (incoming.length + workspace.documents.length > 3) {
      setError(
        "A workspace holds up to three PDFs. Start a new workspace for more.",
      );
      return;
    }
    if (
      incoming.some(
        (f) =>
          !f.name.toLowerCase().endsWith(".pdf") || f.size > 50 * 1024 * 1024,
      )
    ) {
      setError("Choose PDF files up to 50 MB each.");
      return;
    }
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setPhase("Uploading PDFs");
    try {
      const form = new FormData();
      incoming.forEach((file) => form.append("files", file));
      const records = await api<Document[]>("/summarizer/upload", {
        method: "POST",
        body: form,
        signal: abort.signal,
      });
      update((w) => ({
        ...w,
        documents: [
          ...w.documents,
          ...records.filter((d) => !w.documents.some((old) => old.id === d.id)),
        ],
        title:
          w.title === "Untitled workspace"
            ? records[0].filename.replace(/\.pdf$/i, "")
            : w.title,
      }));
      const readyDocuments = await waitDocuments(
        records.map((d) => d.id),
        (docs) => {
          setPhase(
            docs.some((d) => d.status === "indexing")
              ? "Indexing page sources"
              : "Extracting document pages",
          );
          update((w) => ({
            ...w,
            documents: w.documents.map(
              (d) => docs.find((x) => x.id === d.id) || d,
            ),
          }));
        },
        abort.signal,
      );
      setViewDoc(readyDocuments[0]);
      setPage(1);
      setPhase("PDFs ready. Ask a question or choose a review.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      controller.current = null;
      if (filesRef.current) filesRef.current.value = "";
    }
  }
  async function run(
    options: { question?: string; mode?: "quick" | "complete" },
    retry = false,
  ) {
    if (!workspace) return;
    const text = options.question?.trim();
    if (!text && !options.mode) return;
    if (options.mode && !workspace.documents.length) {
      setError("Attach a PDF before starting a review.");
      return;
    }
    if (provider !== "ollama" && (!endpoint || !apiKey)) {
      if (text) setQuestion(text);
      setLastRequest(null);
      setSettings(true);
      setError("Add a compatible endpoint, model ID, and API key in Settings.");
      return;
    }
    setError("");
    setLastRequest(options);
    setBusy(true);
    setProgress(null);
    follow.current = true;
    setPhase("Preparing sources");
    const abort = new AbortController();
    controller.current = abort;
    jobRef.current = null;
    const assistantId = crypto.randomUUID();
    if (!retry)
      append({
        id: crypto.randomUUID(),
        role: "user",
        content:
          text ||
          (options.mode === "complete"
            ? "Review every readable page"
            : "Give me a quick overview"),
        state: "complete",
      });
    append({
      id: assistantId,
      role: "assistant",
      content: "",
      state: "generating",
    });
    try {
      await waitDocuments(
        workspace.documents.map((d) => d.id),
        (docs) => update((w) => ({ ...w, documents: docs })),
        abort.signal,
      );
      const shared = {
        pdf_ids: workspace.documents.map((d) => d.id),
        model,
        answer_length: length,
        provider,
        ...(provider !== "ollama"
          ? { api_base_url: endpoint, api_key: apiKey }
          : {}),
      };
      const request: JobPayload = options.mode
        ? { kind: "summary", payload: { ...shared, mode: options.mode } }
        : {
            kind: "chat",
            payload: {
              ...shared,
              question: text,
              history: historyFor(workspace.messages),
            },
          };
      const job = await api<{ id: string }>("/summarizer/jobs", post(request));
      jobRef.current = job.id;
      try {
        sessionStorage.setItem(
          "documind.chat.job",
          JSON.stringify({
            id: job.id,
            workspace: active,
            assistant: assistantId,
            question: text || "",
            mode: options.mode,
          }),
        );
      } catch {
        setStorageError(
          "This browser cannot retain a reconnect marker. Completed work can still be saved on the backend.",
        );
      }
      if (abort.signal.aborted) {
        await api(`/summarizer/jobs/${job.id}/cancel`, { method: "POST" });
        abort.signal.throwIfAborted();
      }
      let metrics: Metrics = {},
        answer = "",
        terminal = false,
        first: number | undefined;
      const started = performance.now();
      await consumeJob(
        job.id,
        (event) => {
          if (event.type === "metadata") {
            metrics = {
              ...metrics,
              ...event,
              sources: safeSources(event.sources),
            };
            amend(assistantId, (m) => ({ ...m, metrics }));
          }
          if (event.type === "status") {
            setPhase(event.message || "Preparing answer");
            if (
              typeof event.total === "number" &&
              typeof event.completed === "number"
            )
              setProgress({ total: event.total, completed: event.completed });
          }
          if (event.type === "text") {
            first ??= performance.now() - started;
            answer += event.content || "";
            setPhase(
              options.mode === "complete"
                ? "Reviewing document segments"
                : "Writing answer",
            );
            amend(assistantId, (m) => ({ ...m, content: answer, metrics }));
          }
          if (event.type === "done") {
            terminal = true;
            metrics = {
              ...metrics,
              ...event.metrics,
              ttft_ms: Math.round(first || 0),
            };
            amend(assistantId, (m) => ({ ...m, state: "complete", metrics }));
            setPhase("Answer complete");
            setProgress(null);
          }
          if (event.type === "error")
            throw new Error(event.message || "Generation failed");
          if (event.type === "cancelled") {
            terminal = true;
            amend(assistantId, (m) => ({ ...m, state: "cancelled" }));
            setPhase("Generation stopped");
          }
        },
        abort.signal,
      );
      if (!terminal) throw new Error("Answer did not complete");
    } catch (e) {
      const stopped = abort.signal.aborted;
      amend(assistantId, (m) => ({
        ...m,
        state: stopped ? "cancelled" : "failed",
      }));
      if (!stopped) setError(e instanceof Error ? e.message : "Answer failed");
      setPhase(stopped ? "Generation stopped" : "Answer needs attention");
    } finally {
      setBusy(false);
      controller.current = null;
      jobRef.current = null;
      setProgress(null);
    }
  }
  async function stop() {
    const id = jobRef.current;
    controller.current?.abort();
    if (id)
      try {
        await api(`/summarizer/jobs/${id}/cancel`, { method: "POST" });
      } catch {
        setError(
          "The connection was stopped, but server cancellation could not be confirmed. Check the backend.",
        );
      }
  }
  function exportWorkspace() {
    if (!workspace) return;
    const blob = new Blob([JSON.stringify(workspace, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${workspace.title.replace(/[^\w-]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function copy(message: Message) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(message.id);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      setError(
        "Clipboard access was denied. Select the answer text to copy it.",
      );
    }
  }
  const documents = workspace?.documents || [],
    lastAssistant = [...(workspace?.messages || [])]
      .reverse()
      .find((m) => m.role === "assistant"),
    sources = safeSources(lastAssistant?.metrics?.sources);
  const ready =
    documents.length > 0 &&
    documents.every((d) => ["completed", "partial"].includes(d.status));
  return (
    <div className={`app ${rail ? "" : "rail-closed"}`}>
      <aside className="sidebar" aria-label="Workspaces">
        <a className="brand" href="/" aria-label="DocuMind home">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M6 5h12l8 8v14H6zM18 5v9h8M11 19h10M11 23h7" />
          </svg>
          DocuMind<span>Local workspace</span>
        </a>
        <button className="new-workspace" onClick={create} disabled={busy}>
          <Plus size={17} />
          New workspace
        </button>
        <label className="search">
          <Search size={16} />
          <input
            placeholder="Find a workspace"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Find a workspace"
          />
        </label>
        <p className="nav-label">Your workspaces</p>
        <nav>
          {workspaces
            .filter((w) => w.title.toLowerCase().includes(filter.toLowerCase()))
            .map((w) => (
              <button
                key={w.id}
                className={w.id === active ? "workspace active" : "workspace"}
                onClick={() => choose(w)}
                disabled={busy}
              >
                <MessageSquare size={16} />
                <span>
                  {w.title}
                  <small>
                    {w.documents.length
                      ? `${w.documents.length} PDF${w.documents.length === 1 ? "" : "s"}`
                      : "Conversation"}
                  </small>
                </span>
              </button>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <a href={`/study?workspace=${encodeURIComponent(active)}`}>
            <BookOpen size={16} />
            Exam desk
            <ArrowUpRight size={14} />
          </a>
          <div className="service">
            <span
              className={
                health === "Local services ready" ? "dot ready" : "dot"
              }
            />
            {health}
          </div>
          <button onClick={() => setSettings(true)}>
            <SlidersHorizontal size={16} />
            Model & preferences
          </button>
          <a href="http://127.0.0.1:8501" target="_blank" rel="noreferrer">
            Classic interface
            <ArrowUpRight size={14} />
          </a>
        </div>
      </aside>
      <main>
        <header className="workspace-header">
          <button
            className="icon-button"
            aria-label={rail ? "Hide workspaces" : "Show workspaces"}
            onClick={() => setRail(!rail)}
          >
            {rail ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
          </button>
          <div className="scope">
            <h1>{workspace?.title || "Your next discovery"}</h1>
          </div>
          <button className="model-button" onClick={() => setSettings(true)}>
            <span className="dot ready" />
            {model}
            <SlidersHorizontal size={14} />
          </button>
          <button
            ref={evidenceToggle}
            className="icon-button pdf-panel-toggle"
            aria-label={evidenceOpen ? "Hide PDF panel" : "Show PDF panel"}
            title={evidenceOpen ? "Hide PDF panel" : "Show PDF panel"}
            aria-expanded={evidenceOpen}
            aria-controls="pdf-evidence"
            onClick={() =>
              evidenceOpen ? closeEvidence() : setEvidenceOpen(true)
            }
          >
            {evidenceOpen ? (
              <PanelRightClose size={18} />
            ) : (
              <PanelRightOpen size={18} />
            )}
          </button>
          <button
            className="icon-button"
            aria-label="Export conversation"
            onClick={exportWorkspace}
          >
            <Download size={18} />
          </button>
        </header>
        <div className="mobile-tabs">
          <button
            aria-pressed={mobileView === "chat"}
            onClick={() => setMobileView("chat")}
          >
            Conversation
          </button>
          <button
            ref={evidenceTab}
            aria-pressed={mobileView === "evidence"}
            aria-controls="pdf-evidence"
            onClick={() => {
              setEvidenceOpen(true);
              setMobileView("evidence");
            }}
          >
            PDF & evidence {sources.length ? `(${sources.length})` : ""}
          </button>
        </div>
        {storageError && (
          <div className="notice" role="alert">
            {storageError}
            <button onClick={exportWorkspace}>Export conversation</button>
          </div>
        )}
        <div
          className="workbench"
          data-mobile-view={mobileView}
          data-evidence-open={evidenceOpen}
        >
          <section className="conversation" aria-label="Conversation">
            <div className="conversation-toolbar">
              <a
                className="study-entry"
                href={`/study?workspace=${encodeURIComponent(active)}`}
              >
                Exam desk <ArrowUpRight size={14} />
              </a>
              <div>
                <button
                  disabled={!ready || busy}
                  onClick={() => run({ mode: "quick" })}
                >
                  Quick overview
                </button>
                <button
                  disabled={!ready || busy}
                  onClick={() => run({ mode: "complete" })}
                >
                  <BookOpen size={15} />
                  Complete review
                </button>
              </div>
            </div>
            <div
              className="messages"
              ref={scroll}
              onScroll={() => {
                const el = scroll.current;
                if (el)
                  follow.current =
                    el.scrollHeight - el.scrollTop - el.clientHeight < 100;
              }}
            >
              {!workspace?.messages.length ? (
                <div className="empty-conversation">
                  <div className="empty-symbol">
                    <BookOpen size={30} strokeWidth={1.2} />
                  </div>
                  <h2>
                    A little clarity.
                    <br />A better question.
                  </h2>
                  <p>
                    Bring your PDFs into focus. Follow an idea, find the detail,
                    and go straight to the page behind the answer.
                  </p>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => filesRef.current?.click()}
                  >
                    <Plus size={16} />
                    Bring a document
                  </button>
                  <div className="starter-list">
                    <button
                      onClick={() =>
                        setQuestion(
                          "What are the key decisions and their supporting evidence?",
                        )
                      }
                    >
                      Find the key decisions
                      <ArrowUpRight size={16} />
                    </button>
                    <button
                      onClick={() =>
                        setQuestion(
                          "Which claims contradict each other across these documents?",
                        )
                      }
                    >
                      Compare different perspectives
                      <ArrowUpRight size={16} />
                    </button>
                    <button
                      onClick={() =>
                        setQuestion(
                          "Which important questions do these documents leave unanswered?",
                        )
                      }
                    >
                      See what is still unanswered
                      <ArrowUpRight size={16} />
                    </button>
                  </div>
                </div>
              ) : (
                workspace.messages.map((message) => (
                  <article
                    key={message.id}
                    className={`message ${message.role}`}
                  >
                    <div className="message-label">
                      {message.role === "user" ? (
                        "You"
                      ) : (
                        <>
                          <span className="mini-mark">D</span>DocuMind
                        </>
                      )}
                      <span>
                        {message.state === "failed"
                          ? "Failed draft"
                          : message.state === "cancelled"
                            ? "Stopped draft"
                            : message.state === "generating"
                              ? "Working"
                              : ""}
                      </span>
                    </div>
                    {message.role === "assistant" ? (
                      <Answer
                        text={message.content}
                        sources={safeSources(message.metrics?.sources)}
                        onSource={openSource}
                      />
                    ) : (
                      <p className="user-text">{message.content}</p>
                    )}
                    {message.role === "assistant" &&
                      message.state === "generating" &&
                      !message.content && <p className="working">{phase}</p>}
                    {message.role === "assistant" &&
                      message.state === "complete" && (
                        <>
                          <div className="answer-actions">
                            <button
                              onClick={() => copy(message)}
                              aria-label="Copy answer"
                            >
                              {copied === message.id ? (
                                <Check size={14} />
                              ) : (
                                <Copy size={14} />
                              )}{" "}
                              {copied === message.id ? "Copied" : "Copy"}
                            </button>
                            {safeSources(message.metrics?.sources).length >
                              0 && (
                              <span>
                                <ShieldCheck size={14} />
                                {
                                  safeSources(message.metrics?.sources).length
                                }{" "}
                                source pages
                              </span>
                            )}
                            {message.metrics?.contextual_retrieval && (
                              <span>Conversation context used</span>
                            )}
                          </div>
                          <details className="answer-details">
                            <summary>Evidence & response details</summary>
                            <p>{message.metrics?.source_notice}</p>
                            {message.metrics?.citation_warning && (
                              <p className="warning">
                                {message.metrics.citation_warning}
                              </p>
                            )}
                            {message.metrics?.context_notice && (
                              <p>{message.metrics.context_notice}</p>
                            )}
                            {message.metrics?.done_reason === "length" && (
                              <p className="warning">
                                The answer reached its length limit. Choose
                                Longer and ask again.
                              </p>
                            )}
                            {message.metrics?.warnings?.map((w, i) => (
                              <p key={i} className="warning">
                                {w}
                              </p>
                            ))}
                            {message.metrics?.quote_checks?.length ? (
                              <p>
                                {
                                  message.metrics.quote_checks.filter(
                                    (q) => q.verified,
                                  ).length
                                }{" "}
                                explicit quotations matched their cited
                                excerpts. This does not verify paraphrases.
                              </p>
                            ) : null}
                            {typeof message.metrics?.pages_reviewed ===
                              "number" && (
                              <p>
                                {message.metrics.pages_reviewed} readable pages
                                · {message.metrics.segments_reviewed} segments ·{" "}
                                {message.metrics.cache_hits} cached segments
                              </p>
                            )}
                            {typeof message.metrics?.ttft_ms === "number" && (
                              <p>
                                First answer text:{" "}
                                {Math.round(message.metrics.ttft_ms)} ms
                                {typeof message.metrics.tok_per_sec === "number"
                                  ? ` · ${message.metrics.tok_per_sec} tokens/s`
                                  : ""}
                              </p>
                            )}
                            {safeSources(message.metrics?.sources).map((s) => (
                              <button
                                key={s.id}
                                className="source-row"
                                onClick={() => openSource(s)}
                              >
                                {s.filename}
                                <span>
                                  p. {s.page}
                                  <ArrowUpRight size={14} />
                                </span>
                              </button>
                            ))}
                          </details>
                        </>
                      )}
                  </article>
                ))
              )}
              <div ref={bottom} />
            </div>
            <div className="composer-area">
              {error && (
                <div className="error" role="alert">
                  <p>{error}</p>
                  {lastRequest && (
                    <button
                      disabled={busy}
                      onClick={() => run(lastRequest, true)}
                    >
                      <RotateCcw size={14} />
                      Retry request
                    </button>
                  )}
                  <button
                    aria-label="Dismiss error"
                    onClick={() => setError("")}
                  >
                    <X size={15} />
                  </button>
                </div>
              )}
              {phase && (
                <div className="generation-status" role="status">
                  <span className={busy ? "dot working-dot" : "dot ready"} />
                  {phase}
                  {progress && (
                    <span>
                      {progress.completed}/{progress.total}
                    </span>
                  )}
                  {!busy && lastRequest && (
                    <button onClick={() => run(lastRequest, true)}>
                      <RotateCcw size={13} />
                      Run again
                    </button>
                  )}
                </div>
              )}
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!busy && question.trim()) {
                    const text = question;
                    setQuestion("");
                    run({ question: text });
                  }
                }}
              >
                <textarea
                  ref={input}
                  aria-label="Ask DocuMind"
                  placeholder={
                    documents.length
                      ? "Ask about your documents…"
                      : "Ask anything, or bring a PDF…"
                  }
                  value={question}
                  maxLength={8000}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      if (!busy && question.trim()) {
                        const text = question;
                        setQuestion("");
                        run({ question: text });
                      }
                    }
                  }}
                />
                <div className="composer-controls">
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => filesRef.current?.click()}
                    disabled={busy}
                    aria-label="Attach PDFs"
                  >
                    <Paperclip size={18} />
                  </button>
                  <span>
                    {documents.length
                      ? `${documents.length} PDF${documents.length === 1 ? "" : "s"} in context`
                      : "PDFs up to 50 MB · 3 per workspace"}
                  </span>
                  <select
                    aria-label="Answer length"
                    value={length}
                    onChange={(e) => setLength(e.target.value)}
                  >
                    <option value="short">Concise</option>
                    <option value="long">Longer</option>
                  </select>
                  {busy ? (
                    <button
                      type="button"
                      className="send stop"
                      aria-label="Stop generation"
                      onClick={stop}
                    >
                      <Square size={15} />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      className="send"
                      aria-label="Send question"
                      disabled={!question.trim()}
                    >
                      <ArrowUp size={19} />
                    </button>
                  )}
                </div>
              </form>
              <p className="composer-note">
                Answers can be mistaken. The source is always worth a look.
              </p>
              <input
                ref={filesRef}
                type="file"
                multiple
                accept="application/pdf,.pdf"
                aria-label="PDF files"
                className="file-input"
                onChange={(e) => upload(e.target.files)}
              />
            </div>
          </section>
          <section
            id="pdf-evidence"
            className="evidence"
            aria-label="PDF evidence"
          >
            <div className="evidence-header">
              <div>
                <BookOpen size={17} />
                <h2
                  ref={evidenceHeading}
                  tabIndex={-1}
                  aria-label={
                    viewDoc
                      ? `${viewDoc.filename}, PDF page ${page}`
                      : "Source material"
                  }
                >
                  Source material
                </h2>
              </div>
              <div className="evidence-actions">
                <span>{documents.length}/3 PDFs</span>
                <button
                  className="icon-button"
                  aria-label="Close PDF panel"
                  title="Close PDF panel"
                  onClick={closeEvidence}
                >
                  <X size={17} />
                </button>
              </div>
            </div>
            <div className="documents">
              {documents.map((doc) => (
                <button
                  className={
                    viewDoc?.id === doc.id ? "document selected" : "document"
                  }
                  key={doc.id}
                  onClick={() => {
                    setViewDoc(doc);
                    setPage(1);
                    setSelected(null);
                  }}
                >
                  <FileText size={20} />
                  <span>
                    {doc.filename}
                    <small>
                      {doc.page_count ? `${doc.page_count} pages · ` : ""}
                      {doc.status === "completed"
                        ? "Ready to explore"
                        : doc.status}
                    </small>
                  </span>
                  {doc.status === "completed" && <Check size={14} />}
                </button>
              ))}
              <button
                className="add-source"
                disabled={busy || documents.length >= 3}
                onClick={() => filesRef.current?.click()}
              >
                <Plus size={16} />
                {documents.length ? "Add another PDF" : "Attach your first PDF"}
              </button>
            </div>
            {viewDoc ? (
              <>
                <div className="page-toolbar">
                  <span>PDF page</span>
                  <button
                    className="icon-button"
                    aria-label="Previous PDF page"
                    disabled={page <= 1}
                    onClick={() => {
                      setPage((p) => p - 1);
                      setSelected(null);
                    }}
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <input
                    aria-label="PDF page number"
                    type="number"
                    min={1}
                    max={viewDoc.page_count || 99999}
                    value={page}
                    onChange={(e) => {
                      const n = Number(e.target.value);
                      if (n >= 1 && n <= (viewDoc.page_count || 99999)) {
                        setPage(n);
                        setSelected(null);
                      }
                    }}
                  />
                  <span>
                    of{" "}
                    {viewDoc.page_count ||
                      documents.find((d) => d.id === viewDoc.id)?.page_count ||
                      "—"}
                  </span>
                  <button
                    className="icon-button"
                    aria-label="Next PDF page"
                    disabled={
                      page >=
                      (viewDoc.page_count ||
                        documents.find((d) => d.id === viewDoc.id)
                          ?.page_count ||
                        1)
                    }
                    onClick={() => {
                      setPage((p) => p + 1);
                      setSelected(null);
                    }}
                  >
                    <ChevronRight size={16} />
                  </button>
                  <a
                    href={`/api/summarizer/documents/${viewDoc.id}/file#page=${page}`}
                    target="_blank"
                    rel="noreferrer"
                    aria-label="Open original PDF"
                  >
                    <ArrowUpRight size={17} />
                  </a>
                </div>
                <div className="pdf-canvas">
                  {imageError ? (
                    <div className="error">
                      <p>This PDF page could not be displayed.</p>
                      <button onClick={() => setImageError(false)}>
                        Retry page
                      </button>
                    </div>
                  ) : (
                    <PDFPage
                      key={`${viewDoc.id}-${page}`}
                      id={viewDoc.id}
                      page={page}
                      filename={viewDoc.filename}
                      excerpt={selected?.excerpt}
                      onError={() => setImageError(true)}
                    />
                  )}
                </div>
                {selected && (
                  <div
                    className="excerpt"
                    key={`${selected.pdf_id}-${selected.page}`}
                  >
                    <div>
                      <span className="source-index">
                        {selected.id.slice(1)}
                      </span>
                      <strong>Behind this answer</strong>
                      <span>PDF page {selected.page}</span>
                    </div>
                    <p>{selected.excerpt}</p>
                    <small>
                      Extracted text may contain OCR errors. Compare it with the
                      original page.
                    </small>
                  </div>
                )}
              </>
            ) : (
              <div className="evidence-empty">
                <div className="document-outline">
                  <FileText size={48} strokeWidth={1} />
                </div>
                <h3>Keep the evidence close.</h3>
                <p>
                  Open a citation and its original page appears here. No tab
                  switching. No losing your train of thought.
                </p>
                <div className="evidence-example">
                  <ShieldCheck size={17} />
                  <span>Real pages. Traceable answers.</span>
                </div>
              </div>
            )}
            {sources.length > 0 && (
              <div className="source-strip">
                <span>In the latest answer</span>
                {sources.map((s) => (
                  <button
                    key={s.id}
                    className={
                      selected?.id === s.id &&
                      selected?.pdf_id === s.pdf_id &&
                      selected?.page === s.page
                        ? "active"
                        : ""
                    }
                    onClick={() => openSource(s)}
                    aria-label={`View source ${s.id}, PDF page ${s.page}`}
                  >
                    <span>{s.id.slice(1)}</span>Page {s.page}
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
      {settings && (
        <div className="modal-backdrop" onClick={() => setSettings(false)}>
          <section
            className="settings"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSettings(false);
              if (e.key === "Tab") {
                const nodes = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    "button,input,select,a[href]",
                  ),
                );
                const first = nodes[0],
                  last = nodes[nodes.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first.focus();
                }
              }
            }}
          >
            <header>
              <h2 id="settings-title">Make it your workspace</h2>
              <button
                className="icon-button"
                autoFocus
                aria-label="Close settings"
                onClick={() => setSettings(false)}
              >
                <X size={18} />
              </button>
            </header>
            {error && (
              <p role="alert" className="warning">
                {error}
              </p>
            )}
            <p>
              Choose where answers come from. Your local model stays warm
              between questions.
            </p>
            <label>
              Model source
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                disabled={busy}
              >
                <option value="ollama">Local Ollama</option>
                <option value="openai-compatible" disabled={localOnly}>
                  Compatible API
                  {localOnly ? " (disabled in local-only mode)" : ""}
                </option>
              </select>
            </label>
            {provider === "ollama" ? (
              <label>
                Installed model
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={busy}
                >
                  {[...new Set([model, ...models])].map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </label>
            ) : (
              <>
                <label>
                  Model ID
                  <input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    disabled={busy}
                  />
                </label>
                <label>
                  API base URL
                  <input
                    placeholder="https://provider.example/v1"
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                    disabled={busy}
                  />
                </label>
                <label>
                  API key
                  <input
                    type="password"
                    autoComplete="off"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    disabled={busy}
                  />
                  <small>
                    Kept in memory for this browser session. Sent to your local
                    backend for provider requests.
                  </small>
                </label>
              </>
            )}
            <div className="settings-note">
              <ShieldCheck size={18} />
              <p>
                Browser conversations stay in this browser. Original PDFs and
                indexes stay in your local backend. The classic interface keeps
                its separate conversation history.
              </p>
            </div>
            <button className="primary" onClick={() => setSettings(false)}>
              Back to the work
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
