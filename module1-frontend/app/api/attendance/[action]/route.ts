import { NextResponse } from "next/server";
import { AUTH_BACKEND_URL, authErrorMessage } from "@/lib/authBackend";

export async function POST(request: Request, { params }: { params: Promise<{ action: string }> }) {
  const routes: Record<string, string> = { resolve: "/attendance/resolve", checkin: "/checkins/" };
  const path = routes[(await params).action];
  if (!path) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return NextResponse.json({ detail: "Please sign in." }, { status: 401 });
  const body = await request.text();
  if (body.length > 3_000_000) return NextResponse.json({ detail: "Capture is too large. Please try again." }, { status: 413 });
  try {
    const response = await fetch(`${AUTH_BACKEND_URL}/api/v1${path}`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: authorization },
      body, cache: "no-store", signal: AbortSignal.timeout(90000),
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(response.ok ? data : { detail: authErrorMessage(data.detail, "Unable to complete check-in.") },
      { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Attendance service is unavailable. Please try again." }, { status: 503 });
  }
}
