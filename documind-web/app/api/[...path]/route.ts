import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (
    !(
      path[0] === "summarizer" ||
      (path.length === 1 && path[0] === "healthz")
    ) ||
    path.some((p) => p === ".." || p.includes("/"))
  )
    return Response.json({ detail: "Route not found" }, { status: 404 });
  const base = process.env.DOCUMIND_BACKEND_URL || "http://127.0.0.1:8888";
  const headers = new Headers();
  for (const name of ["content-type", "range"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const options: RequestInit & { duplex?: string } = {
      method: request.method,
      headers,
      cache: "no-store",
      signal: request.signal,
    };
    if (!["GET", "HEAD"].includes(request.method)) {
      options.body = request.body;
      options.duplex = "half";
    }
    const response = await fetch(
      `${base}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      options,
    );
    const outgoing = new Headers();
    for (const name of [
      "content-type",
      "content-disposition",
      "content-range",
      "accept-ranges",
      "retry-after",
    ]) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    outgoing.set("Cache-Control", "no-store");
    outgoing.set("X-Content-Type-Options", "nosniff");
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        detail: "The local backend is unavailable. Check Docker and try again.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
