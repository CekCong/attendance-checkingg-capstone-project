import { NextResponse } from "next/server";
import { isInstructorApp } from "@/lib/appSurface";
import { AUTH_BACKEND_URL, authErrorMessage } from "@/lib/authBackend";

const REFRESH_COOKIE = "refresh_token";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    email?: string;
    password?: string;
  };

  if (
    !body || typeof body.email !== "string" || !body.email.trim() ||
    typeof body.password !== "string" || !body.password
  ) {
    return NextResponse.json({ detail: "Email and password are required" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${AUTH_BACKEND_URL}/api/v1/auth/login`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: body.email.trim(),
          password: body.password,
        }),
        signal: AbortSignal.timeout(15000),
      },
    );
  } catch {
    return NextResponse.json(
      { detail: "Unable to reach the account service. Please try again shortly." },
      { status: 503 },
    );
  }

  const data = await backendResponse.json().catch(() => ({}));

  if (!backendResponse.ok) {
    return NextResponse.json(
      {
        detail: authErrorMessage(data.detail, "Login failed"),
      },
      {
        status: backendResponse.status,
      },
    );
  }

  if (
    isInstructorApp() &&
    data.user?.role !== "instructor" &&
    data.user?.role !== "admin"
  ) {
    return NextResponse.json(
      { detail: "Instructor access required" },
      { status: 403 },
    );
  }

  const response = NextResponse.json({
    access_token: data.access_token,
    token_type: data.token_type ?? "bearer",
    user: data.user,
  });

  if (data.refresh_token) {
    response.cookies.set(
      REFRESH_COOKIE,
      data.refresh_token,
      {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 60 * 60 * 24 * 7,
      },
    );
  }

  return response;
}
