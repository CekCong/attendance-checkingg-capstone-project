import { NextResponse } from "next/server";
import { AUTH_BACKEND_URL } from "@/lib/authBackend";

async function forward(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const resource = path.join("/");
  const allowed = /^(users\/me(?:\/face\/enroll)?|devices(?:\/[a-zA-Z0-9-]+)?|sessions\/[a-zA-Z0-9-]+|checkins(?:\/[a-zA-Z0-9-]+)?|enrollments\/my-enrollments|auth\/password|attendance\/resolve)$/.test(resource);
  if (!allowed) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return NextResponse.json({ detail: "Please sign in." }, { status: 401 });
  const body = request.method === "GET" ? undefined : await request.text();
  if (body && body.length > 30_000_000) return NextResponse.json({ detail: "Capture is too large." }, { status: 413 });
  const suffix = new URL(request.url).pathname.endsWith("/") ? "/" : "";
  try {
    const upstream = await fetch(`${AUTH_BACKEND_URL}/api/v1/${resource}${suffix}${new URL(request.url).search}`, {
      method: request.method, body, cache: "no-store", signal: AbortSignal.timeout(90_000),
      headers: { Authorization: authorization, "Content-Type": "application/json" },
    });
    const content = await upstream.text();
    return new Response(content || null, { status: upstream.status, headers: {
      "Content-Type": "application/json", "Cache-Control": "no-store",
    } });
  } catch {
    return NextResponse.json({ detail: "Attendance service is unavailable. Please try again." }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
