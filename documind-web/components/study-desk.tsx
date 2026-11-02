"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  Download,
  FileText,
  Plus,
  Search,
  Square,
  Upload,
  X,
} from "lucide-react";
import { Answer } from "./answer";
import { ExamRunner, ExamAnswers, type ExamAnswer } from "./exam-runner";
import { WorkspaceTransfer } from "./workspace-transfer";
import { LanguageSelect } from "./language-select";
import { api, post, consumeJob, waitDocuments } from "../lib/api";
import {
  loadSavedWorkspaces,
  persistWorkspace,
  downloadText,
} from "../lib/persistence";
import {
  newWorkspace,
  restoreWorkspaces,
  safeSources,
} from "../lib/workspaces";
import {
  equationPreview,
  generatedPracticePrompt,
  inputMarkdown,
  dueItems,
  staleEvidence,
} from "../lib/study";
import type {
  Calculation,
  MathInput,
  PaperQuestion,
  StudyItem,
} from "../lib/study";
import type { Workspace, Source, Metrics, Document } from "../lib/types";

const starter: MathInput = {
  operation: "solve",
  expression: "x^2 - 5*x + 6 = 0",
  variable: "x",
  domain: "real",
};
export function StudyDesk() {
  const [spaces, setSpaces] = useState<Workspace[]>([]),
    [active, setActive] = useState(""),
    [tab, setTab] = useState("paper");
  const [tool, setTool] = useState<MathInput>(starter),
    [extra, setExtra] = useState(""),
    [working, setWorking] = useState("");
  const [mathWorking, setMathWorking] = useState("");
  const [answerLanguage, setAnswerLanguage] = useState('auto');
  const [examBusy, setExamBusy] = useState(false);
  const [examAnswers, setExamAnswers] = useState<ExamAnswer[]>([]);
  const examResultsHeading = useRef<HTMLHeadingElement>(null);
  const [question, setQuestion] = useState(""),
    [mode, setMode] = useState("explain"),
    [task, setTask] = useState("problem");
  const [model, setModel] = useState("llama3.2:3b"),
    [models, setModels] = useState<string[]>([]),
    [rubric, setRubric] = useState("");
  const [answer, setAnswer] = useState(""),
    [calculation, setCalculation] = useState<Calculation | null>(null),
    [metrics, setMetrics] = useState<Metrics>({});
  const [sources, setSources] = useState<Source[]>([]),
    [selected, setSelected] = useState<Source | null>(null);
  const [items, setItems] = useState<StudyItem[]>([]),
    [questions, setQuestions] = useState<PaperQuestion[]>([]),
    [paper, setPaper] = useState(0),
    [selectedQuestion, setSelectedQuestion] = useState("");
  const [busy, setBusy] = useState(false),
    [phase, setPhase] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [copied, setCopied] = useState(false);
  const [kind, setKind] = useState("formula"),
    [note, setNote] = useState(""),
    [filter, setFilter] = useState(""),
    [storage, setStorage] = useState<Record<string, number>>({});
  const [vision, setVision] = useState(false),
    [practiceTopic, setPracticeTopic] = useState("quadratic");
  const [visionModels, setVisionModels] = useState<string[]>([]),
    [visionModel, setVisionModel] = useState("qwen3-vl:2b-instruct");
  const [versions, setVersions] = useState<Record<number, string>>({});
  const [availableDocs, setAvailableDocs] = useState<Document[]>([]),
    [backupLink, setBackupLink] = useState("");
  const revisions = useRef<Record<string, number>>({}),
    controller = useRef<AbortController | null>(null),
    job = useRef<string | null>(null);
  const importRef = useRef<HTMLInputElement>(null),
    imageRef = useRef<HTMLInputElement>(null),
    uploadRef = useRef<HTMLInputElement>(null);
  const resumed = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const space = spaces.find((s) => s.id === active),
    docs = space?.documents || [];
  async function refreshItems(id = active) {
    if (id)
      setItems(
        await api<StudyItem[]>(
          `/summarizer/study/items/${encodeURIComponent(id)}`,
        ),
      );
  }
  useEffect(() => {
    loadSavedWorkspaces()
      .then(async (saved) => {
        revisions.current = saved.revisions;
        let values = saved.values;
        if (!values.length) {
          try {
            values = restoreWorkspaces(
              localStorage.getItem("documind.workspaces.v2"),
            ).filter(w=>!saved.deletedIds.includes(w.id));
          } catch {}
          if (!values.length) values = [newWorkspace()];
          for (const w of values)
            revisions.current[w.id] = (await persistWorkspace(w)).revision;
        }
        setSpaces(values);
        const requested = new URLSearchParams(location.search).get("workspace");
        setActive(values.find((w) => w.id === requested)?.id || values[0].id);
      })
      .catch((e) => setError(e.message));
    api<{ installed: string[]; default?: string }>("/summarizer/models")
      .then((v) => {
        setModels(v.installed);
        if(v.default && v.installed.includes(v.default))setModel(v.default);
        else if (v.installed.length && !v.installed.includes(model))
          setModel(v.installed[0]);
      })
      .catch(() => {});
    api<Document[]>("/summarizer/library")
      .then((v) => {
        if (Array.isArray(v)) setAvailableDocs(v);
      })
      .catch(() => {});
    api<{ installed: string[] }>("/summarizer/study/vision-models")
      .then((v) => {
        if (v.installed?.length) {
          setVisionModels(v.installed);
          setVisionModel(v.installed[0]);
        }
      })
      .catch(() => {});
    return () => {
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    refreshItems().catch((e) => setError(e.message));
    setQuestions([]);
    setExamAnswers([]);
    setPaper(0);
    setAnswer("");
    setCalculation(null);
    setSources([]);
    setSelected(null);
    setMetrics({});
  }, [active]);
  useEffect(() => {
    if (model && models.includes(model))
      api("/summarizer/models/preload", post({ model })).catch(() => {});
  }, [model, models]);
  useEffect(() => {
    if (calculation || answer) {
      resultHeading.current?.scrollIntoView?.({
        block: "start",
        behavior: "instant",
      });
      resultHeading.current?.focus({ preventScroll: true });
    }
  }, [calculation, Boolean(answer)]);
  useEffect(() => {
    if (!docs.length) {
      setVersions({});
      return;
    }
    api<{ pdf_id: number; text_sha256: string }[]>(
      `/summarizer/study/document-versions?${docs.map((d) => `ids=${d.id}`).join("&")}`,
    )
      .then((values) => {
        if (Array.isArray(values))
          setVersions(
            Object.fromEntries(values.map((v) => [v.pdf_id, v.text_sha256])),
          );
      })
      .catch(() => {});
  }, [active, docs.map((d) => d.id).join(",")]);
  useEffect(() => {
    if (!active || resumed.current) return;
    let saved: {
      id: string;
      workspace: string;
      question: string;
      task?: string;
      mode?: string;
    } | null = null;
    try {
      saved = JSON.parse(
        sessionStorage.getItem("documind.study.job") || "null",
      );
    } catch {}
    if (!saved || saved.workspace !== active) return;
    resumed.current = true;
    const pending = saved;
    const abort = new AbortController();
    controller.current = abort;
    job.current = pending.id;
    setQuestion(pending.question);
    if (pending.task) setTask(pending.task);
    if (pending.mode) setMode(pending.mode);
    setBusy(true);
    setPhase("Reconnecting to saved progress");
    let text = "",
      details: Metrics = {};
    consumeJob(
      pending.id,
      (event) => {
        if (event.type === "metadata") {
          details = { ...details, ...event };
          setMetrics(details);
          setSources(safeSources(event.sources));
          if (event.math) setCalculation(event.math as Calculation);
        }
        if (event.type === "text") {
          text += event.content || "";
          setAnswer(text);
        }
        if (event.type === "status") setPhase(event.message || "Reconnecting");
        if (event.type === "done") {
          details = { ...details, ...event.metrics };
          setMetrics(details);
          setPhase("Recovered completed answer");
        }
        if (event.type === "error")
          throw new Error(
            event.message || "The interrupted draft needs a retry.",
          );
        if (event.type === "cancelled")
          setPhase("Recovered stopped draft — incomplete");
      },
      abort.signal,
    )
      .then(() => {
        setNotice(
          "Saved progress recovered. Completed results remain available in this tab; save an important result to your library.",
        );
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(e.message);
          setPhase("Recovered draft — retry required");
        }
      })
      .finally(() => {
        if (!abort.signal.aborted)
          sessionStorage.removeItem("documind.study.job");
        setBusy(false);
        job.current = null;
        controller.current = null;
      });
  }, [active]);
  async function saveSpace(w: Workspace) {
    const saved = await persistWorkspace(w, revisions.current[w.id]);
    revisions.current[w.id] = saved.revision;
    setSpaces((v) =>
      v.some((s) => s.id === w.id)
        ? v.map((s) => (s.id === w.id ? w : s))
        : [w, ...v],
    );
  }
  async function saveItem(
    itemKind: string,
    data: Record<string, unknown>,
    id?: string,
  ) {
    if (!active) return;
    await api(
      "/summarizer/study/items",
      post({
        workspace_id: active,
        kind: itemKind,
        data,
        ...(id ? { id } : {}),
      }),
    );
    await refreshItems();
    setNotice("Saved to this workspace.");
  }
  async function action(fn: () => Promise<void>) {
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "This action failed.");
    }
  }
  function mathPayload(): MathInput {
    const value = { ...tool };
    if (tool.operation === "matrix")
      value.matrix = JSON.parse(extra || "[[1,2],[3,4]]");
    if (tool.operation === "solve" && extra.trim()) {
      value.equations = extra.split("\n").filter(Boolean);
      value.variables = Array.from(
        new Set(
          value.equations.join("").match(/\b[a-z]\b/g) || [tool.variable],
        ),
      );
    }
    if (mathWorking.trim())
      value.working = mathWorking.split("\n").filter(Boolean);
    return value;
  }
  async function calculate() {
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setPhase("Calculating and checking");
    setAnswer("");
    setCalculation(null);
    setSources([]);
    setMetrics({});
    try {
      const result = await api<Calculation>("/summarizer/study/solve", {
        ...post(mathPayload()),
        signal: abort.signal,
      });
      setCalculation(result);
      setPhase(
        result.verified
          ? "Calculation checks passed"
          : "Result ready; review the listed checks",
      );
      await saveItem("attempt", {
        question: tool.expression,
        result,
        mode: "calculator",
        checked: result.verified,
        created: new Date().toISOString(),
      });
      const prior = items.find((i) => i.kind === "active_problem");
      await saveItem(
        "active_problem",
        {
          question: `User equation: ${tool.expression}. Operation: ${tool.operation}. Calculator result: ${result.result}.`,
        },
        prior?.id,
      );
    } catch (e) {
      if (abort.signal.aborted)
        setPhase(
          "Request stopped. The bounded calculator process finishes within its time limit.",
        );
      else {
        setPhase("Calculation needs attention");
        throw e;
      }
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }
  async function assist(approvedMath?: MathInput) {
    if (!question.trim()) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setAnswer("");
    setCalculation(null);
    setSources([]);
    setMetrics({});
    let text = "",
      resultMetrics: Metrics = {};
    try {
      const focus = items.find((i) => i.kind === "active_problem");
      const created = await api<{ id: string }>("/summarizer/study/jobs", {
        ...post({
          question,
          answer_language: answerLanguage,
          mode,
          task,
          pdf_ids: docs.filter(d=>!selectedQuestion || d.id!==paper).map((d) => d.id),
          model,
          answer_length: "long",
          working,
          rubric,
          ...(approvedMath ? { math: approvedMath } : {}),
          focus_problem: focus
            ? String(focus.data.question || "").slice(0, 1200)
            : "",
        }),
        signal: abort.signal,
      });
      job.current = created.id;
      try {
        sessionStorage.setItem(
          "documind.study.job",
          JSON.stringify({
            id: created.id,
            workspace: active,
            question,
            task,
            mode,
          }),
        );
      } catch {
        setNotice(
          "Browser reconnection is unavailable; completed study items will still be saved on this computer.",
        );
      }
      await consumeJob(
        created.id,
        (event) => {
          if (event.type === "status") setPhase(event.message || "Working");
          if (event.type === "metadata") {
            resultMetrics = { ...resultMetrics, ...event };
            setMetrics(resultMetrics);
            setSources(safeSources(event.sources));
            if (event.math) setCalculation(event.math as Calculation);
          }
          if (event.type === "text") {
            text += event.content || "";
            setAnswer(text);
            setPhase("Writing the explanation");
          }
          if (event.type === "done") {
            resultMetrics = { ...resultMetrics, ...event.metrics };
            setMetrics(resultMetrics);
            setPhase(
              event.metrics?.awaiting_interpretation
                ? "Review interpreted inputs before calculation"
                : "Study answer complete",
            );
          }
          if (event.type === "cancelled")
            setPhase("Stopped draft — incomplete");
          if (event.type === "error")
            throw new Error(event.message || "Study task failed");
        },
        abort.signal,
      );
      if (!abort.signal.aborted) {
        await saveItem("attempt", {
          question,
          answer: text,
          metrics: resultMetrics,
          mode,
          task,
          created: new Date().toISOString(),
        });
        const prior = items.find((i) => i.kind === "active_problem");
        await saveItem("active_problem", { question }, prior?.id);
      }
    } catch (e) {
      if (abort.signal.aborted) setPhase("Stopped draft — incomplete");
      else {
        setPhase("Failed draft — incomplete");
        throw e;
      }
    } finally {
      setBusy(false);
      job.current = null;
      controller.current = null;
      if (!abort.signal.aborted)
        try {
          sessionStorage.removeItem("documind.study.job");
        } catch {}
    }
  }
  async function stop() {
    controller.current?.abort();
    if (job.current)
      await api(`/summarizer/jobs/${job.current}/cancel`, { method: "POST" });
    sessionStorage.removeItem("documind.study.job");
  }
  async function loadPaper(id: number) {
    setPaper(id);
    const value = await api<{ questions: PaperQuestion[]; notice: string }>(
      `/summarizer/study/papers/${id}`,
    );
    setQuestions(value.questions);
    setNotice(value.notice);
  }
  async function upload(files: FileList | null) {
    if (!files?.length || !space) return;
    if (files.length + docs.length > 3)
      throw new Error("Use up to three PDFs per workspace.");
    setBusy(true);
    setPhase("Uploading and indexing PDFs");
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append("files", f));
      const records = await api<Document[]>("/summarizer/upload", {
        method: "POST",
        body: form,
      });
      const abort = new AbortController();
      controller.current = abort;
      const ready = await waitDocuments(
        records.map((d) => d.id),
        () => {},
        abort.signal,
      );
      await saveSpace({
        ...space,
        documents: [
          ...docs,
          ...ready.filter((d) => !docs.some((old) => old.id === d.id)),
        ],
        updated: Date.now(),
      });
      setPhase("PDFs ready");
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }
  async function transcribe(file: File | undefined) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024)
      throw new Error("Choose an image up to 8 MB.");
    setBusy(true);
    setPhase("Transcribing image");
    try {
      let value: { text: string; notice: string };
      if (vision) {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        value = await api(
          "/summarizer/study/vision",
          post({ model: visionModel, image_base64: base64 }),
        );
      } else {
        const form = new FormData();
        form.append("image", file);
        value = await api("/summarizer/study/transcribe", {
          method: "POST",
          body: form,
        });
      }
      setQuestion(value.text);
      setNotice(value.notice);
      setTab("solve");
    } finally {
      setBusy(false);
    }
  }
  async function importBackup(file: File | undefined) {
    if (!file) return;
    if (file.size > 2_000_000) throw new Error("Choose a backup up to 2 MB.");
    const raw = JSON.parse(await file.text());
    const value = restoreWorkspaces(JSON.stringify([raw.workspace || raw]))[0];
    if (!value) throw new Error("This is not a valid workspace backup.");
    const w = {
      ...value,
      id: crypto.randomUUID(),
      title: `${value.title} (imported)`,
    };
    await saveSpace(w);
    setActive(w.id);
    if (Array.isArray(raw.items))
      for (const item of raw.items.slice(0, 500))
        await api(
          "/summarizer/study/items",
          post({ workspace_id: w.id, kind: item.kind, data: item.data }),
        );
    setNotice(
      "Backup imported as a separate workspace. PDF IDs require the same local document library.",
    );
  }
  const resultText =
    answer ||
    (calculation
      ? `## Calculated result\n\n$$\n${calculation.latex}\n$$\n\n` +
        calculation.steps.map((s, i) => `${i + 1}. ${s}`).join("\n")
      : "");
  return (
    <div className="study-app">
      <header className="study-header">
        <a href="/" className="study-brand">
          <BookOpen size={22} />
          DocuMind
        </a>
        <a href="/" className="study-back">
          <ArrowLeft size={16} />
          PDF conversations
        </a>
        <div className="study-scope">
          <label className="sr-only" htmlFor="study-workspace">
            Study workspace
          </label>
          <select
            id="study-workspace"
            value={active}
            disabled={busy || examBusy}
            onChange={(e) => setActive(e.target.value)}
          >
            {spaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.title}
              </option>
            ))}
          </select>
        </div>
        <button
          aria-label="New study workspace"
          disabled={busy}
          onClick={() =>
            action(async () => {
              const w = newWorkspace();
              await saveSpace(w);
              setActive(w.id);
            })
          }
        >
          <Plus size={17} />
        </button>
        <button
          aria-label="Import study backup"
          onClick={() => importRef.current?.click()}
        >
          <Upload size={17} />
        </button>
        <a
          aria-label="Export study backup"
          href={`/api/summarizer/workspaces/${encodeURIComponent(active)}/export`}
        >
          <Download size={17} />
        </a>
      </header>
      <div className="study-title">
        <div>
          <h1>Exam desk</h1>
          <p>Answer a question paper from your source PDFs.</p>
        </div>
        <span className="study-local">Saved on this computer</span>
      </div>
      <WorkspaceTransfer workspace={active} disabled={busy||examBusy}/>
      <nav className="study-tabs" aria-label="Study tools">
        {[
          ["solve", "Solve & explain"],
          ["paper", "Exam paper"],
          ["review", "Review queue"],
          ["library", "Study library"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => {
              setTab(key);
              if (key === "library")
                api<Record<string, number>>("/summarizer/study/storage")
                  .then(setStorage)
                  .catch(() => {});
            }}
          >
            {label}
            {key === "review" && dueItems(items).length > 0 ? (
              <span>{dueItems(items).length}</span>
            ) : null}
          </button>
        ))}
      </nav>
      {error && (
        <div className="study-alert error" role="alert">
          <p>{error}</p>
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {notice && (
        <div className="study-alert" role="status">
          {notice}
        </div>
      )}
      {tab === "solve" && (
        <div className="study-grid">
          <section className="study-input" aria-label="Problem input">
            <h2>A question worth understanding.</h2>
            <p className="study-muted">
              Type a problem, bring a page, or check an equation directly.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action(assist);
              }}
            >
              <label htmlFor="study-question">Your question</label>
              <textarea
                id="study-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                maxLength={8000}
                placeholder="A ball is thrown upward at 20 m/s. When does it reach its highest point?"
                rows={4}
              />
              <div className="study-form-row">
                <label>
                  Task
                  <select
                    value={task}
                    onChange={(e) => setTask(e.target.value)}
                  >
                    <option value="problem">Solve a problem</option>
                    <option value="notes">Explain from notes</option>
                    <option value="compare">Compare documents</option>
                    <option value="synthesis">Consolidate findings</option>
                    <option value="practice">Generate practice</option>
                    <option value="check">Review my working</option>
                  </select>
                </label>
                <label>
                  Response
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="explain">Worked explanation</option>
                    <option value="answer">Answer & checks</option>
                    <option value="hint">Give a hint</option>
                    <option value="quiz">Quiz me</option>
                    <option value="check">Check my attempt</option>
                  </select>
                </label>
              </div>
              <div className="study-actions">
                <button className="primary" disabled={busy || !question.trim()}>
                  Work this question
                  <ArrowUpRight size={16} />
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => imageRef.current?.click()}
                >
                  <Upload size={16} />
                  Read an image
                </button>
              </div>
              <label>
                Local model
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                >
                  {(models.length ? models : [model]).map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </label>
              <LanguageSelect value={answerLanguage} onChange={setAnswerLanguage} disabled={busy}/>
              <details>
                <summary>Student working & marking rubric</summary>
                <label>
                  My working
                  <textarea
                    value={working}
                    onChange={(e) => setWorking(e.target.value)}
                    rows={3}
                    maxLength={4000}
                  />
                </label>
                <label>
                  Supplied marking rubric
                  <textarea
                    value={rubric}
                    onChange={(e) => setRubric(e.target.value)}
                    rows={3}
                    maxLength={4000}
                  />
                </label>
                <p className="study-muted">
                  Marks from a model remain provisional. Save a rubric with the
                  question to revisit it.
                </p>
                <button
                  type="button"
                  onClick={() =>
                    action(() => saveItem("rubric", { question, rubric }))
                  }
                >
                  Save rubric
                </button>
              </details>
            </form>
            <label className="study-checkbox">
              <input
                type="checkbox"
                checked={vision}
                onChange={(e) => setVision(e.target.checked)}
              />
              Use the selected vision model for diagrams (must be installed)
            </label>
            {vision && (
              <label>
                Image reader model
                <select
                  aria-label="Image reader model"
                  value={visionModel}
                  onChange={(e) => setVisionModel(e.target.value)}
                >
                  {(visionModels.length ? visionModels : [visionModel]).map(
                    (m) => (
                      <option key={m}>{m}</option>
                    ),
                  )}
                </select>
                <small className="study-muted">
                  Image interpretation is editable and unverified. Check every
                  mathematical symbol before submitting.
                </small>
              </label>
            )}
            <details className="calculator" open>
              <summary>
                Equation calculator{" "}
                <span>Runs locally · checks supported operations</span>
              </summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(calculate);
                }}
              >
                <div className="study-form-row">
                  <label>
                    Operation
                    <select
                      aria-label="Calculation operation"
                      value={tool.operation}
                      onChange={(e) => {
                        setTool({ ...starter, operation: e.target.value });
                        setExtra("");
                      }}
                    >
                      {[
                        "solve",
                        "simplify",
                        "factor",
                        "differentiate",
                        "integrate",
                        "numeric",
                        "matrix",
                        "check",
                        "units",
                      ].map((o) => (
                        <option key={o} value={o}>
                          {o[0].toUpperCase() + o.slice(1)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Domain
                    <select
                      value={tool.domain}
                      onChange={(e) =>
                        setTool({ ...tool, domain: e.target.value })
                      }
                    >
                      <option value="real">Real numbers</option>
                      <option value="complex">Complex numbers</option>
                    </select>
                  </label>
                </div>
                {!["matrix", "units"].includes(tool.operation) && (
                  <>
                    <label>
                      Equation or expression
                      <input
                        aria-label="Equation or expression"
                        value={tool.expression}
                        onChange={(e) =>
                          setTool({ ...tool, expression: e.target.value })
                        }
                        maxLength={500}
                      />
                    </label>
                    <div
                      className="equation-preview"
                      aria-label="Equation preview"
                    >
                      <Answer
                        text={`$$\n${equationPreview(tool.expression)}\n$$`}
                        sources={[]}
                        onSource={() => {}}
                      />
                    </div>
                    <div className="math-keys">
                      {["^2", "sqrt(x)", "pi", "sin(x)", "\\frac{x}{2}"].map(
                        (symbol) => (
                          <button
                            type="button"
                            key={symbol}
                            onClick={() =>
                              setTool({
                                ...tool,
                                expression: tool.expression + symbol,
                              })
                            }
                          >
                            {symbol === "\\frac{x}{2}" ? "Fraction" : symbol}
                          </button>
                        ),
                      )}
                    </div>
                    <p className="study-muted">
                      Use x^2, 2*x, sqrt(x), or simple LaTeX fractions. Angles
                      use radians.
                    </p>
                    <label>
                      Variable
                      <input
                        value={tool.variable}
                        maxLength={1}
                        onChange={(e) =>
                          setTool({ ...tool, variable: e.target.value })
                        }
                      />
                    </label>
                  </>
                )}
                {tool.operation === "solve" && (
                  <label>
                    System of equations (optional, one per line)
                    <textarea
                      value={extra}
                      onChange={(e) => setExtra(e.target.value)}
                      placeholder={"x+y=5\nx-y=1"}
                      rows={2}
                    />
                  </label>
                )}
                {tool.operation === "integrate" && (
                  <div className="study-form-row">
                    <label>
                      Lower bound (optional)
                      <input
                        value={tool.lower || ""}
                        onChange={(e) =>
                          setTool({
                            ...tool,
                            lower: e.target.value || undefined,
                          })
                        }
                      />
                    </label>
                    <label>
                      Upper bound
                      <input
                        value={tool.upper || ""}
                        onChange={(e) =>
                          setTool({
                            ...tool,
                            upper: e.target.value || undefined,
                          })
                        }
                      />
                    </label>
                  </div>
                )}
                {tool.operation === "check" && (
                  <label>
                    Compare with
                    <input
                      value={tool.expected || ""}
                      onChange={(e) =>
                        setTool({ ...tool, expected: e.target.value })
                      }
                    />
                  </label>
                )}
                {tool.operation === "matrix" && (
                  <>
                    <label>
                      Square matrix (JSON)
                      <textarea
                        value={extra}
                        onChange={(e) => setExtra(e.target.value)}
                        placeholder="[[1,2],[3,4]]"
                      />
                    </label>
                    <label>
                      Matrix operation
                      <select
                        value={tool.matrix_action || "determinant"}
                        onChange={(e) =>
                          setTool({ ...tool, matrix_action: e.target.value })
                        }
                      >
                        <option value="determinant">Determinant</option>
                        <option value="inverse">Inverse</option>
                        <option value="eigenvalues">
                          Eigenvalues and multiplicities
                        </option>
                      </select>
                    </label>
                  </>
                )}
                {tool.operation === "units" && (
                  <>
                    <label>
                      Value
                      <input
                        type="number"
                        step="any"
                        value={tool.magnitude ?? 1}
                        onChange={(e) =>
                          setTool({
                            ...tool,
                            magnitude: Number(e.target.value),
                          })
                        }
                      />
                    </label>
                    <div className="study-form-row">
                      <label>
                        From
                        <input
                          value={tool.from_unit || "m"}
                          onChange={(e) =>
                            setTool({ ...tool, from_unit: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        To
                        <input
                          value={tool.to_unit || "cm"}
                          onChange={(e) =>
                            setTool({ ...tool, to_unit: e.target.value })
                          }
                        />
                      </label>
                    </div>
                  </>
                )}
                <details>
                  <summary>Check algebraic steps (optional)</summary>
                  <label>
                    One equivalent expression or equation per line
                    <textarea
                      value={mathWorking}
                      onChange={(e) => setMathWorking(e.target.value)}
                      rows={3}
                      placeholder={"(x-2)*(x-3)=0\nx=2"}
                    />
                  </label>
                  <p className="study-muted">
                    This compares expressions or solution sets, including lost
                    roots. It does not check prose proofs.
                  </p>
                </details>
                <button className="primary" disabled={busy}>
                  Calculate & check
                  <ArrowUpRight size={16} />
                </button>
              </form>
            </details>
          </section>
          <section className="study-output" aria-label="Solution">
            <div className="solution-heading">
              <h2 ref={resultHeading} tabIndex={-1}>
                Your working space
              </h2>
              {busy && (
                <button onClick={() => action(stop)}>
                  <Square size={14} />
                  Stop
                </button>
              )}
            </div>
            <p className="study-phase" role="status">
              {phase ||
                "An explanation you can inspect, with the evidence beside it."}
            </p>
            {metrics.awaiting_interpretation ? null : resultText ? (
              <>
                <article className="solution-paper">
                  {calculation && (
                    <details open className="calculation-input">
                      <summary>Inputs used for this calculation</summary>
                      <Answer
                        text={inputMarkdown(calculation.input)}
                        sources={[]}
                        onSource={() => {}}
                      />
                      <p className="study-muted">
                        Check that these inputs match your question. The
                        calculation checks apply to these inputs.
                      </p>
                    </details>
                  )}
                  <Answer
                    text={resultText}
                    sources={sources}
                    onSource={setSelected}
                  />
                  {calculation && (
                    <div className="calculation-checks">
                      <p>
                        <Check size={16} />
                        {calculation.verified
                          ? "Listed calculation checks passed"
                          : "Review the check results"}
                      </p>
                      {calculation.checks.map((c, i) => (
                        <p key={i} className={c.passed ? "" : "warning"}>
                          {c.passed ? "Passed" : "Unverified"} · {c.label}
                        </p>
                      ))}
                      {calculation.working_checks.map((c) => (
                        <p key={c.step} className={c.passed ? "" : "warning"}>
                          Working line {c.step}: {c.label}
                        </p>
                      ))}
                      <details>
                        <summary>Assumptions & interpretation</summary>
                        <p>Input: {calculation.input.expression}</p>
                        {calculation.assumptions.map((a) => (
                          <p key={a}>{a}</p>
                        ))}
                        <p>
                          The calculator verifies its inputs. Check that those
                          inputs represent your question.
                        </p>
                      </details>
                    </div>
                  )}
                </article>
                <div className="study-actions">
                  <button
                    onClick={() =>
                      action(async () => {
                        await navigator.clipboard.writeText(
                          calculation?.latex || resultText,
                        );
                        setCopied(true);
                      })
                    }
                  >
                    <Copy size={15} />
                    {copied ? "Copied" : "Copy LaTeX / answer"}
                  </button>
                  <button
                    onClick={() =>
                      downloadText(
                        "documind-solution.md",
                        resultText,
                        "text/markdown",
                      )
                    }
                  >
                    <Download size={15} />
                    Export solution
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        saveItem("mistake", {
                          question: question || tool.expression,
                          answer: resultText,
                          note: "Review this problem",
                          due: new Date().toISOString(),
                          interval_days: 0,
                        }),
                      )
                    }
                  >
                    Revisit this problem
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        saveItem("formula", {
                          question: question || tool.expression,
                          answer: resultText,
                          latex: calculation?.latex,
                          sources,
                        }),
                      )
                    }
                  >
                    Save to formula sheet
                  </button>
                </div>
              </>
            ) : (
              <div className="solution-empty">
                <div className="empty-equation">
                  <Answer
                    text={"$$\nx=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}\n$$"}
                    sources={[]}
                    onSource={() => {}}
                  />
                </div>
                <h3>From question to understanding.</h3>
                <p>
                  Start with the equation on the left, or ask about a problem in
                  your notes. Calculations and retrieved evidence stay visibly
                  separate.
                </p>
                <p className="study-muted">
                  Algebra · calculus · matrices · units
                </p>
              </div>
            )}
            {metrics.interpretation ? (
              <div className="interpretation-review">
                {metrics.awaiting_interpretation && (
                  <>
                    <h3>Check the interpreted inputs</h3>
                    <p>
                      The question was translated into calculator inputs. Confirm the equation
                      and values represent it before calculating.
                    </p>
                    <Answer
                      text={inputMarkdown(
                        (metrics.interpretation as { math: MathInput }).math,
                      )}
                      sources={[]}
                      onSource={() => {}}
                    />
                    <button
                      className="primary"
                      disabled={busy || question !== metrics.request_question}
                      onClick={() => {
                        const value = (
                          metrics.interpretation as { math?: MathInput }
                        ).math;
                        if (value) action(() => assist(value));
                      }}
                    >
                      Calculate these inputs
                      <ArrowUpRight size={16} />
                    </button>
                    {question !== metrics.request_question && (
                      <p>
                        Submit your edited question again before calculating.
                      </p>
                    )}
                  </>
                )}
                <details className="study-metadata">
                  <summary>Review the model’s problem interpretation</summary>
                  <pre>{JSON.stringify(metrics.interpretation, null, 2)}</pre>
                  <button
                    onClick={() => {
                      const value = metrics.interpretation as {
                        math?: MathInput;
                      };
                      if (value.math) setTool(value.math);
                    }}
                  >
                    Edit in calculator
                  </button>
                </details>
              </div>
            ) : null}
            {sources.length > 0 && (
              <div className="study-evidence">
                <h3>Evidence from your PDFs</h3>
                <p>
                  {String(
                    metrics.source_notice ||
                      "Citations locate evidence; derived answers are calculated separately.",
                  )}
                </p>
                {sources.map((s) => (
                  <button
                    key={`${s.pdf_id}-${s.page}`}
                    onClick={() => setSelected(s)}
                  >
                    <FileText size={16} />
                    {s.filename}
                    <span>p. {s.page}</span>
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
            )}
            {selected && (
              <aside className="study-source">
                <div>
                  <h3>
                    {selected.filename} · p. {selected.page}
                  </h3>
                  <button
                    aria-label="Close source"
                    onClick={() => setSelected(null)}
                  >
                    <X size={16} />
                  </button>
                </div>
                <p>{selected.excerpt}</p>
                <a
                  href={`/api/summarizer/documents/${selected.pdf_id}/file#page=${selected.page}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open original PDF
                  <ArrowUpRight size={14} />
                </a>
                <button
                  onClick={() =>
                    action(() =>
                      saveItem("bookmark", {
                        ...selected,
                        title: `${selected.filename} · p. ${selected.page}`,
                      }),
                    )
                  }
                >
                  Bookmark page
                </button>
                <label>
                  Your note on this page
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={4000}
                    rows={2}
                  />
                </label>
                <button
                  onClick={() =>
                    action(async () => {
                      await saveItem("annotation", {
                        ...selected,
                        title: `${selected.filename} · p. ${selected.page}`,
                        answer: note,
                        sources: [selected],
                      });
                      setNote("");
                    })
                  }
                  disabled={!note.trim()}
                >
                  Save linked annotation
                </button>
              </aside>
            )}
            {Object.keys(metrics).length > 0 && (
              <details className="study-metadata">
                <summary>Timing & verification details</summary>
                <p>
                  Retrieval: {String(metrics.retrieval_ms ?? "—")} ms · Search
                  rounds: {String(metrics.search_queries ?? "—")} · Reranker:{" "}
                  {String(metrics.reranker ?? "—")}
                </p>
                <p>
                  Model: {model} · Total pipeline:{" "}
                  {String(metrics.pipeline_ms ?? "—")} ms
                </p>
                <p className="warning">
                  Source IDs, quoted text and tool checks do not verify every
                  sentence of a generated explanation.
                </p>
              </details>
            )}
          </section>
        </div>
      )}
      {tab === "paper" && (
        <div className="study-grid paper-grid">
          <section className="study-input">
            <h2>Answer a paper.</h2>
            <p className="study-muted">
              Choose the question paper and your source documents. Direct answers retain their source pages.
            </p>
            <label>
              Exam PDF
              <select
                value={paper}
                disabled={busy || examBusy}
                onChange={(e) =>
                  action(() => loadPaper(Number(e.target.value)))
                }
              >
                <option value={0}>Choose a document</option>
                {[...new Map([...docs,...availableDocs].map(d=>[d.id,d])).values()].map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={busy} onClick={() => uploadRef.current?.click()}>
              <Plus size={16} />
              Add PDF
            </button>
            <ExamRunner key={active} workspaceId={active} paper={paper} documents={docs} model={model} language={answerLanguage} onLanguage={setAnswerLanguage} onBusy={setExamBusy} answers={examAnswers} onAnswers={setExamAnswers} onViewResults={()=>{examResultsHeading.current?.scrollIntoView({block:'start'});examResultsHeading.current?.focus({preventScroll:true});}} onSaved={()=>{refreshItems().catch(e=>setError(e.message));}} onPaper={d=>{setAvailableDocs(current=>[...current.filter(item=>item.id!==d.id),d]);action(()=>loadPaper(d.id));}}/>
            <details className="paper-questions" open={!examAnswers.length}>
              <summary>Detected questions ({questions.length})</summary>
              {questions.map((q, i) => {
                const key = `q-${q.pdf_id}-${q.number}-${i}`,
                  status = items.find(
                    (item) =>
                      item.kind === "question_status" && item.data.key === key,
                  );
                return (
                  <button
                    key={key}
                    disabled={examBusy}
                    aria-pressed={selectedQuestion === key}
                    onClick={() => {
                      setSelectedQuestion(key);
                      setExamAnswers([]);
                      setQuestion(q.text);
                    }}
                  >
                    <strong>Question {q.number}</strong>
                    <span className="paper-question-preview">{q.text.length > 240 ? `${q.text.slice(0, 240)}…` : q.text}</span>
                    <small>
                      p. {q.page}
                      {q.marks ? ` · ${q.marks} marks` : ""} ·{" "}
                      {String(status?.data.status || "Unanswered")}
                    </small>
                  </button>
                );
              })}
            </details>
            {paper && !questions.length ? (
              <p>
                No numbered questions detected. Copy a question from the
                original PDF, or use image transcription.
              </p>
            ) : null}
          </section>
          <section className="study-output">
            <h2 ref={examResultsHeading} tabIndex={-1}>{examAnswers.length?'Answers from your references':'The selected question'}</h2>
            {examAnswers.length ? <ExamAnswers rows={examAnswers} busy={examBusy} onReview={(text,input)=>{setQuestion(text);setTool(input);setExtra((input.equations||[]).join('\n'));setSelectedQuestion('exam-review');setTask('problem');setTab('solve');setNotice('Review the equation, then use Calculate & check.');}}/> : <>
            <textarea
              aria-label="Selected exam question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={8}
            />
            <div className="study-actions">
              <button
                className="primary"
                onClick={() => {
                  setTask("problem");
                  setTab("solve");
                }}
              >
                Open in solver
                <ArrowUpRight size={16} />
              </button>
              <button
                onClick={() =>
                  action(() =>
                    saveItem(
                      "question_status",
                      { key: selectedQuestion, status: "Attempted", question },
                      items.find(
                        (i) =>
                          i.kind === "question_status" &&
                          i.data.key === selectedQuestion,
                      )?.id,
                    ),
                  )
                }
              >
                Mark attempted
              </button>
              <button
                onClick={() =>
                  action(() =>
                    saveItem(
                      "question_status",
                      { key: selectedQuestion, status: "Checked", question },
                      items.find(
                        (i) =>
                          i.kind === "question_status" &&
                          i.data.key === selectedQuestion,
                      )?.id,
                    ),
                  )
                }
              >
                Mark checked
              </button>
            </div>
            {paper > 0 && (
              <a
                href={`/api/summarizer/documents/${paper}/file`}
                target="_blank"
                rel="noreferrer"
              >
                Open the original paper
                <ArrowUpRight size={16} />
              </a>
            )}
            </>}
          </section>
        </div>
      )}
      {tab === "review" && (
        <section className="study-collection">
          <h2>A little practice, remembered.</h2>
          <div className="study-actions">
            <label>
              Practice topic
              <select
                value={practiceTopic}
                onChange={(e) => setPracticeTopic(e.target.value)}
              >
                <option value="quadratic">Quadratic equations</option>
                <option value="linear">Linear equations</option>
                <option value="derivative">Derivatives</option>
                <option value="integral">Integrals</option>
              </select>
            </label>
            <button
              disabled={busy}
              onClick={() =>
                action(async () => {
                  setBusy(true);
                  try {
                    await api(
                      "/summarizer/study/practice",
                      post({
                        workspace_id: active,
                        topic: practiceTopic,
                        count: 3,
                      }),
                    );
                    await refreshItems();
                    setNotice(
                      "Three generated exercises saved with calculator-checked answers. Reveal each answer after attempting it.",
                    );
                  } finally {
                    setBusy(false);
                  }
                })
              }
            >
              Build checked practice
              <Plus size={16} />
            </button>
          </div>
          <p className="study-muted">
            Due dates use your attempts: review tomorrow after a miss; double
            the interval after a correct recall, up to 90 days.
          </p>
          {dueItems(items).length === 0 ? (
            <p>
              No reviews due. Save a difficult problem or formula to start a
              revision queue.
            </p>
          ) : (
            dueItems(items).map((item) => (
              <article className="review-row" key={item.id}>
                {generatedPracticePrompt(item) ? <>
                  <h3>{generatedPracticePrompt(item)!.label}</h3>
                  <Answer text={generatedPracticePrompt(item)!.markdown} sources={[]} onSource={() => {}} />
                </> : <h3>
                  {String(
                    item.data.question || item.data.title || "Saved review",
                  )}
                </h3>}
                <details>
                  <summary>Reveal saved answer</summary>
                  <Answer
                    text={String(item.data.answer || item.data.note || "")}
                    sources={safeSources(item.data.sources)}
                    onSource={(s) =>
                      window.open(
                        `/api/summarizer/documents/${s.pdf_id}/file#page=${s.page}`,
                        "_blank",
                        "noopener",
                      )
                    }
                  />
                </details>
                <div className="study-actions">
                  <button
                    onClick={() =>
                      action(async () => {
                        await api(
                          `/summarizer/study/items/${item.id}/review`,
                          post({ workspace_id: active, correct: false }),
                        );
                        await refreshItems();
                      })
                    }
                  >
                    Needs another look
                  </button>
                  <button
                    onClick={() =>
                      action(async () => {
                        await api(
                          `/summarizer/study/items/${item.id}/review`,
                          post({ workspace_id: active, correct: true }),
                        );
                        await refreshItems();
                      })
                    }
                  >
                    <Check size={15} />
                    Recalled correctly
                  </button>
                </div>
              </article>
            ))
          )}
        </section>
      )}
      {tab === "library" && (
        <section className="study-collection">
          <div className="library-heading">
            <div>
              <h2>Your study library</h2>
              <p className="study-muted">
                Formulas, mistakes, attempts, annotations and backups belong to
                this workspace.
              </p>
            </div>
            <label className="search">
              <Search size={16} />
              <input
                aria-label="Search saved study work"
                placeholder="Find a saved idea"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </label>
          </div>
          <details>
            <summary>Add a note, formula or bookmark</summary>
            <label>
              Kind
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {[
                  "formula",
                  "mistake",
                  "annotation",
                  "bookmark",
                  "topic",
                  "practice",
                ].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label>
              Note (Markdown / LaTeX)
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
              />
            </label>
            <button
              onClick={() =>
                action(async () => {
                  await saveItem(kind, {
                    title: note.slice(0, 80),
                    answer: note,
                    due: new Date().toISOString(),
                  });
                  setNote("");
                })
              }
            >
              Save note
            </button>
          </details>
          {items
            .filter(
              (i) =>
                i.kind !== "active_problem" &&
                JSON.stringify(i.data)
                  .toLowerCase()
                  .includes(filter.toLowerCase()),
            )
            .map((item) => (
              <article className="library-row" key={item.id}>
                {staleEvidence(item.data, versions) && (
                  <p className="warning">
                    This answer used an older extracted document version.
                    Recheck its evidence.
                  </p>
                )}
                <div>
                  <span>{item.kind.replaceAll("_", " ")}</span>
                  <h3>
                    {String(
                      item.data.question ||
                        item.data.title ||
                        item.data.key ||
                        "Saved study work",
                    )}
                  </h3>
                </div>
                <details>
                  <summary>Open saved work</summary>
                  {typeof item.data.pdf_id === "number" &&
                    typeof item.data.page === "number" && (
                      <a
                        href={`/api/summarizer/documents/${item.data.pdf_id}/file#page=${item.data.page}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open linked PDF page
                        <ArrowUpRight size={14} />
                      </a>
                    )}
                  <Answer
                    text={String(
                      item.data.answer ||
                        item.data.note ||
                        item.data.rubric ||
                        "",
                    )}
                    sources={safeSources(
                      item.data.sources ||
                        (item.data.metrics as Metrics)?.sources,
                    )}
                    onSource={(s) =>
                      window.open(
                        `/api/summarizer/documents/${s.pdf_id}/file#page=${s.page}`,
                        "_blank",
                        "noopener",
                      )
                    }
                  />
                  {item.data.result ? (
                    <Answer
                      text={`$$\n${String((item.data.result as Calculation).latex)}\n$$`}
                      sources={[]}
                      onSource={() => {}}
                    />
                  ) : null}
                  <button
                    onClick={() => {
                      setQuestion(String(item.data.question || ""));
                      setTab("solve");
                    }}
                  >
                    Reopen question
                  </button>
                  <button
                    onClick={() =>
                      action(async () => {
                        await api(
                          `/summarizer/study/items/${item.id}?workspace_id=${encodeURIComponent(active)}`,
                          { method: "DELETE" },
                        );
                        await refreshItems();
                      })
                    }
                  >
                    Remove saved item
                  </button>
                </details>
              </article>
            ))}
          <details className="library-documents">
            <summary>Documents & workspace storage</summary>
            <label>
              Add an existing PDF
              <select
                aria-label="Add existing PDF"
                value=""
                disabled={busy || docs.length >= 3}
                onChange={(e) => {
                  const document = availableDocs.find(
                    (d) => d.id === Number(e.target.value),
                  );
                  if (document && space)
                    action(() =>
                      saveSpace({ ...space, documents: [...docs, document] }),
                    );
                }}
              >
                <option value="">Choose from the local document library</option>
                {availableDocs
                  .filter(
                    (d) =>
                      !docs.some((old) => old.id === d.id) &&
                      ["completed", "partial"].includes(d.status),
                  )
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.filename}
                    </option>
                  ))}
              </select>
            </label>
            {docs.map((d) => (
              <div className="library-document" key={d.id}>
                <span>{d.filename}</span>
                <button
                  onClick={() =>
                    action(async () => {
                      const name = prompt("PDF display name", d.filename);
                      if (!name) return;
                      const renamed = await api<Document>(
                        `/summarizer/documents/${d.id}`,
                        {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ filename: name }),
                        },
                      );
                      if (space)
                        await saveSpace({
                          ...space,
                          documents: docs.map((old) =>
                            old.id === d.id ? renamed : old,
                          ),
                        });
                    })
                  }
                >
                  Rename
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api(`/summarizer/documents/${d.id}/reindex`, {
                        method: "POST",
                      });
                      setNotice(
                        "Reindexing started. The original PDF is retained.",
                      );
                    })
                  }
                >
                  Reindex
                </button>
                <button
                  onClick={() =>
                    action(async () => {
                      if (space)
                        await saveSpace({
                          ...space,
                          documents: docs.filter((old) => old.id !== d.id),
                        });
                      setNotice(
                        "Removed from this workspace. The original file remains available to other workspaces.",
                      );
                    })
                  }
                >
                  Remove from workspace
                </button>
              </div>
            ))}
            <button onClick={() => uploadRef.current?.click()}>Add PDF</button>
            <button
              onClick={() =>
                action(async () => {
                  const value = await api<{ download: string; notice: string }>(
                    "/summarizer/study/backup",
                    { method: "POST" },
                  );
                  setBackupLink("/api" + value.download);
                  setNotice(value.notice);
                })
              }
            >
              Back up local database
            </button>
            {backupLink && (
              <a href={backupLink}>
                Download database backup
                <Download size={15} />
              </a>
            )}
            <p>
              Review cache: {storage.review_cache_entries ?? "—"} entries ·{" "}
              {storage.review_cache_bytes ?? "—"} bytes
            </p>
            <button
              onClick={() =>
                action(async () => {
                  const value = await api<{ removed: number }>(
                    "/summarizer/study/cache/trim",
                    { method: "POST" },
                  );
                  setNotice(`${value.removed} excess cache entries removed.`);
                  setStorage(await api("/summarizer/study/storage"));
                })
              }
            >
              Trim excess cache
            </button>
            <button
              onClick={() =>
                action(async () => {
                  if (
                    !confirm(
                      "Clear reusable review segments? Original PDFs and saved answers are retained.",
                    )
                  )
                    return;
                  await api("/summarizer/study/cache", { method: "DELETE" });
                  setStorage(await api("/summarizer/study/storage"));
                })
              }
            >
              Clear review cache
            </button>
            <button
              onClick={() =>
                action(async () => {
                  if (!space) return;
                  const title = prompt("Workspace name", space.title);
                  if (title) await saveSpace({ ...space, title });
                })
              }
            >
              Rename workspace
            </button>
            <button
              onClick={() =>
                action(async () => {
                  if (
                    !confirm(
                      "Remove this workspace and its study items? Export a backup first if needed.",
                    )
                  )
                    return;
                  await api(
                    `/summarizer/workspaces/${encodeURIComponent(active)}`,
                    { method: "DELETE" },
                  );
                  const remaining = spaces.filter((w) => w.id !== active);
                  setSpaces(remaining);
                  if (remaining.length) setActive(remaining[0].id);
                  else {
                    const w = newWorkspace();
                    await saveSpace(w);
                    setActive(w.id);
                  }
                })
              }
            >
              Remove workspace
            </button>
          </details>
        </section>
      )}
      <input
        hidden
        ref={importRef}
        type="file"
        accept="application/json"
        onChange={(e) => action(() => importBackup(e.target.files?.[0]))}
      />
      <input
        hidden
        ref={imageRef}
        type="file"
        accept="image/png,image/jpeg"
        onChange={(e) => action(() => transcribe(e.target.files?.[0]))}
      />
      <input
        hidden
        ref={uploadRef}
        type="file"
        multiple
        accept="application/pdf"
        onChange={(e) => action(() => upload(e.target.files))}
      />
    </div>
  );
}
