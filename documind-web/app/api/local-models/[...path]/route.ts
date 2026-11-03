import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  const allowed =
    request.method === "GET"
      ? endpoint === "catalog" || /^jobs\/[a-f0-9]{32}$/.test(endpoint)
      : request.method === "POST" &&
        (["preview", "install"].includes(endpoint) ||
          /^jobs\/[a-f0-9]{32}\/cancel$/.test(endpoint));
  if (!allowed)
    return Response.json({ detail: "Route not found" }, { status: 404 });
  if (
    !["localhost", "127.0.0.1", "[::1]"].includes(request.nextUrl.hostname) ||
    (request.headers.get("origin") &&
      request.headers.get("origin") !== request.nextUrl.origin) ||
    request.headers.get("sec-fetch-site") === "cross-site" ||
    (request.method === "POST" &&
      request.headers.get("origin") !== request.nextUrl.origin)
  ) {
    return Response.json(
      { detail: "Open the installer from this local DocuMind window." },
      { status: 403 },
    );
  }
  const port = Number(process.env.DOCUMIND_MODEL_MANAGER_PORT);
  const token = process.env.DOCUMIND_MODEL_MANAGER_TOKEN;
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) {
    return Response.json(
      {
        detail:
          "Open DocuMind using Start_DocuMind.bat to enable the Windows model installer. Installed models remain usable.",
      },
      { status: 503 },
    );
  }
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && Buffer.byteLength(body) > 4096)
    return Response.json(
      { detail: "Installer request too large" },
      { status: 413 },
    );
  try {
    const response = await fetch(`http://127.0.0.1:${port}/${endpoint}`, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body,
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]),
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "The local model installer disconnected. Keep DocuMind open and retry.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
