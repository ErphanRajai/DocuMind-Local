import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Answer } from "../components/answer";
import {
  restoreWorkspaces,
  historyFor,
  safeSources,
  newWorkspace,
} from "../lib/workspaces";
import { api, decodeEvents, consumeJob, waitDocuments } from "../lib/api";

const source = {
  id: "S1",
  pdf_id: 1,
  page: 2,
  filename: "garden.pdf",
  excerpt: "Budget: 240 dollars.",
};
describe("evidence rendering", () => {
  it("opens the metadata's actual page", () => {
    const select = vi.fn();
    render(
      <Answer
        text="The budget is 240 dollars. [S1]"
        sources={[source]}
        onSource={select}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Open source S1, PDF page 2" }),
    );
    expect(select).toHaveBeenCalledWith(source);
  });
  it("keeps unknown markers and code unlinked", () => {
    render(
      <Answer
        text={"Unknown [S9]. Code `[S1]`."}
        sources={[source]}
        onSource={() => {}}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("[S1]")).toHaveProperty("tagName", "CODE");
  });
  it("does not render source HTML", () => {
    const { container } = render(
      <Answer
        text={"<script>alert(1)</script>"}
        sources={[]}
        onSource={() => {}}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
  });
});
describe("saved workspaces", () => {
  it.each([null, "invalid", "{}", "[null]"])(
    "handles malformed storage %s",
    (raw) => expect(restoreWorkspaces(raw)).toEqual([]),
  );
  it("restores interrupted drafts explicitly", () => {
    const w = newWorkspace();
    w.messages = [
      { id: "a", role: "assistant", content: "Draft", state: "generating" },
    ];
    expect(restoreWorkspaces(JSON.stringify([w]))[0].messages[0].state).toBe(
      "cancelled",
    );
  });
  it("excludes failed evidence from history and bounds messages", () => {
    const messages = Array.from({ length: 12 }, (_, i) => ({
      id: String(i),
      role: "user" as const,
      content: "hello",
      state: "complete" as const,
    }));
    expect(historyFor(messages)).toHaveLength(8);
    expect(
      historyFor([
        { id: "x", role: "assistant", content: "false", state: "failed" },
      ]),
    ).toEqual([]);
  });
  it("rejects forged source locations", () => {
    expect(
      safeSources([
        source,
        { ...source, page: -1 },
        { ...source, pdf_id: "../etc" },
      ]),
    ).toEqual([source]);
  });
});
it("leaves room for the latest question inside the API history limit", () => {
  const history = historyFor(
    Array.from({ length: 8 }, (_, i) => ({
      id: String(i),
      role: "assistant" as const,
      content: "x".repeat(16000),
      state: "complete" as const,
    })),
  );
  expect(
    history.reduce((n, m) => n + m.content.length, 0) + 8000,
  ).toBeLessThanOrEqual(64000);
  expect(history).toHaveLength(3);
});

describe("generation protocol", () => {
  it("decodes UTF-8 and NDJSON split across bytes", async () => {
    const bytes = new TextEncoder().encode(
      '{"type":"text","content":"café 🌱"}\n{"type":"done"}\n',
    );
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
        c.close();
      },
    });
    const result = [];
    for await (const event of decodeEvents(stream)) result.push(event);
    expect(result[0].content).toBe("café 🌱");
    expect(result[1].type).toBe("done");
  });
  it("rejects truncated events", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new TextEncoder().encode('{"type":"done"}'));
        c.close();
      },
    });
    await expect(async () => {
      for await (const _ of decodeEvents(stream)) {
      }
    }).rejects.toThrow("mid-event");
  });
  it("rejects success without a terminal event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response('{"type":"text","content":"draft"}\n')),
    );
    await expect(
      consumeJob("x", () => {}, new AbortController().signal),
    ).rejects.toThrow("before completion");
    vi.unstubAllGlobals();
  });
  it("surfaces backend validation detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "PDF missing" }), {
            status: 404,
          }),
      ),
    );
    await expect(api("/test")).rejects.toThrow("PDF missing");
    vi.unstubAllGlobals();
  });
  it("polls until indexed without uploading again", async () => {
    let count = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              id: 1,
              filename: "garden.pdf",
              status: ++count === 1 ? "indexing" : "completed",
            }),
          ),
      ),
    );
    const update = vi.fn();
    const docs = await waitDocuments(
      [1],
      update,
      new AbortController().signal,
      0,
    );
    expect(docs[0].status).toBe("completed");
    expect(update).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });
  it("reports processing failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              id: 1,
              filename: "garden.pdf",
              status: "failed",
              error_message: "OCR unavailable",
            }),
          ),
      ),
    );
    await expect(
      waitDocuments([1], () => {}, new AbortController().signal, 0),
    ).rejects.toThrow("OCR unavailable");
    vi.unstubAllGlobals();
  });
});
