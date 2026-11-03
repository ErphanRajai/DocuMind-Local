// @vitest-environment node
import { it, expect, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "../app/api/local-models/[...path]/route";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const context = (path: string) => ({
  params: Promise.resolve({ path: path.split("/") }),
});
it("requires a running host installer without exposing its token", async () => {
  vi.stubEnv("DOCUMIND_MODEL_MANAGER_TOKEN", "");
  const response = await GET(
    new NextRequest("http://localhost/api/local-models/catalog"),
    context("catalog"),
  );
  expect(response.status).toBe(503);
  expect((await response.json()).detail).toContain("Start_DocuMind.bat");
});
it("blocks foreign origins and the private console execution route", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const foreign = await POST(
    new NextRequest("http://localhost/api/local-models/install", {
      method: "POST",
      headers: { origin: "https://elsewhere.example" },
      body: "{}",
    }),
    context("install"),
  );
  expect(foreign.status).toBe(403);
  const run = await POST(
    new NextRequest(
      "http://localhost/api/local-models/jobs/" + "a".repeat(32) + "/run",
      { method: "POST" },
    ),
    context("jobs/" + "a".repeat(32) + "/run"),
  );
  expect(run.status).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});
it("forwards only to loopback with a server-side credential", async () => {
  vi.stubEnv("DOCUMIND_MODEL_MANAGER_PORT", "12345");
  vi.stubEnv("DOCUMIND_MODEL_MANAGER_TOKEN", "local-test-token");
  const fetcher = vi.fn(
    async (_input: string, _options?: RequestInit) =>
      new Response('{"id":"public-job"}', { status: 202 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const response = await POST(
    new NextRequest("http://localhost/api/local-models/install", {
      method: "POST",
      headers: { origin: "http://localhost" },
      body: '{"preview_id":"abc"}',
    }),
    context("install"),
  );
  expect(response.status).toBe(202);
  expect(fetcher.mock.calls[0][0]).toBe("http://127.0.0.1:12345/install");
  expect(
    new Headers(fetcher.mock.calls[0][1]?.headers).get("Authorization"),
  ).toBe("Bearer local-test-token");
  expect(await response.text()).not.toContain("local-test-token");
  expect(response.headers.get("cache-control")).toBe("no-store");
});
it("rejects non-local request hosts and oversized payloads", async () => {
  vi.stubEnv("DOCUMIND_MODEL_MANAGER_PORT", "12345");
  vi.stubEnv("DOCUMIND_MODEL_MANAGER_TOKEN", "local-test-token");
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  expect(
    (
      await GET(
        new NextRequest("http://attacker.example/api/local-models/catalog"),
        context("catalog"),
      )
    ).status,
  ).toBe(403);
  const large = await POST(
    new NextRequest("http://localhost/api/local-models/preview", {
      method: "POST",
      headers: { origin: "http://localhost" },
      body: "x".repeat(5000),
    }),
    context("preview"),
  );
  expect(large.status).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});
