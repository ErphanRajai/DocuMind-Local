import type { Workspace, Message } from "./types";
export const STORAGE_KEY = "documind.workspaces.v2";
export function newWorkspace(): Workspace {
  return {
    id: crypto.randomUUID(),
    title: "Untitled workspace",
    documents: [],
    messages: [],
    updated: Date.now(),
  };
}
export function restoreWorkspaces(raw: string | null): Workspace[] {
  if (!raw) return [];
  try {
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data
      .filter(
        (w) =>
          w &&
          typeof w.id === "string" &&
          typeof w.title === "string" &&
          Array.isArray(w.documents) &&
          Array.isArray(w.messages),
      )
      .map((w) => ({
        ...w,
        documents: w.documents.filter(
          (d: unknown) =>
            d &&
            typeof d === "object" &&
            "id" in d &&
            Number.isInteger(d.id) &&
            "filename" in d &&
            typeof d.filename === "string",
        ),
        messages: w.messages
          .filter(
            (m: Message) =>
              m &&
              ["user", "assistant"].includes(m.role) &&
              typeof m.content === "string",
          )
          .map((m: Message) =>
            m.state === "generating" ? { ...m, state: "cancelled" } : m,
          ),
      }));
  } catch {
    return [];
  }
}
export function historyFor(messages: Message[]) {
  const recent = messages
    .filter(
      (m) =>
        m.state !== "failed" &&
        m.state !== "cancelled" &&
        m.state !== "generating",
    )
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 16000) }));
  // Leave 8,000 characters for the next question inside the API's combined
  // 64,000-character validation bound. Model token budgeting happens later.
  let room = 56000;
  const selected: typeof recent = [];
  for (const message of recent.reverse()) {
    if (message.content.length > room) break;
    selected.unshift(message);
    room -= message.content.length;
  }
  return selected;
}
export function safeSources(value: unknown) {
  return Array.isArray(value)
    ? value.filter(
        (s) =>
          s &&
          /^S[1-9]\d*$/.test(s.id) &&
          Number.isInteger(s.pdf_id) &&
          s.pdf_id > 0 &&
          Number.isInteger(s.page) &&
          s.page > 0 &&
          typeof s.excerpt === "string",
      )
    : [];
}
