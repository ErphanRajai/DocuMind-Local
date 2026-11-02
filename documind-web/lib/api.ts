import type { Document, StreamEvent } from "./types";
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let detail = "Request failed. Try again.";
    try {
      const value = await response.json();
      if (typeof value.detail === "string") detail = value.detail;
      else if (Array.isArray(value.detail))
        detail = value.detail.map((e: { msg: string }) => e.msg).join("; ");
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}
export function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export async function* decodeEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader(),
    decoder = new TextDecoder();
  let pending = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      let index;
      while ((index = pending.indexOf("\n")) >= 0) {
        const line = pending.slice(0, index);
        pending = pending.slice(index + 1);
        if (line.trim()) {
          const event = JSON.parse(line);
          if (!event || typeof event.type !== "string")
            throw new Error("Invalid generation event");
          yield event;
        }
      }
      if (pending.length > 2_000_000)
        throw new Error("Generation event is too large");
      if (done) break;
    }
    if (pending.trim())
      throw new Error("The generation connection ended mid-event");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export async function consumeJob(
  id: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(`/api/summarizer/jobs/${id}/events`, { signal });
  if (!response.ok || !response.body)
    throw new Error("Generation expired or disconnected. Retry your request.");
  let terminal = false;
  for await (const event of decodeEvents(response.body)) {
    onEvent(event);
    if (["done", "error", "cancelled"].includes(event.type)) terminal = true;
  }
  if (!terminal)
    throw new Error(
      "The connection ended before completion. Retry your request.",
    );
}
export async function waitDocuments(
  ids: number[],
  onUpdate: (docs: Document[]) => void,
  signal: AbortSignal,
  interval = 900,
): Promise<Document[]> {
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    signal.throwIfAborted();
    const docs = await Promise.all(
      ids.map((id) => api<Document>(`/summarizer/documents/${id}`, { signal })),
    );
    onUpdate(docs);
    const failed = docs.find((d) => d.status === "failed");
    if (failed)
      throw new Error(
        `${failed.filename}: ${failed.error_message || "Processing failed"}`,
      );
    if (docs.every((d) => ["completed", "partial"].includes(d.status)))
      return docs;
    await new Promise<void>((resolve, reject) => {
      const cancel = () => {
        clearTimeout(timer);
        reject(new DOMException("Stopped", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", cancel);
        resolve();
      }, interval);
      signal.addEventListener("abort", cancel, { once: true });
    });
  }
  throw new Error(
    "PDF processing is taking longer than expected. Retry to check its saved status.",
  );
}
