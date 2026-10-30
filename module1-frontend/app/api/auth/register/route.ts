import { NextResponse } from "next/server";
import { isInstructorApp } from "@/lib/appSurface";
import { AUTH_BACKEND_URL, authErrorMessage } from "@/lib/authBackend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (
    !body ||
    typeof body.full_name !== "string" || !body.full_name.trim() ||
    typeof body.email !== "string" || !body.email.trim() ||
    typeof body.password !== "string" || body.password.length < 8
  ) {
    return NextResponse.json(
      { detail: "Enter your full name, email, and a password of at least 8 characters." },
      { status: 400 },
    );
  }
  if (new TextEncoder().encode(body.password).length > 72) {
    return NextResponse.json(
      { detail: "Password is too long. Use at most 72 bytes (fewer characters for some symbols)." },
      { status: 400 },
    );
  }

  try {
    const backendResponse = await fetch(`${AUTH_BACKEND_URL}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: body.full_name.trim(),
        email: body.email.trim(),
        password: body.password,
        // The portal determines the account role; never accept a client-supplied role.
        role: isInstructorApp() ? "instructor" : "student",
      }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await backendResponse.json().catch(() => ({}));
    if (!backendResponse.ok) {
      return NextResponse.json(
        { detail: authErrorMessage(data.detail, "Unable to create your account.") },
        { status: backendResponse.status },
      );
    }
    return NextResponse.json(data, { status: 201 });
  } catch {
    return NextResponse.json(
      { detail: "Unable to reach the account service. Please try again shortly." },
      { status: 503 },
    );
  }
}
