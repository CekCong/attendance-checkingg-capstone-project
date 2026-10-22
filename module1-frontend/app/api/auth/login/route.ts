import { NextResponse } from "next/server";
import { isInstructorApp } from "@/lib/appSurface";

const REFRESH_COOKIE = "refresh_token";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    email?: string;
    password?: string;
  };

  if (!body.email?.trim() || !body.password) {
    return NextResponse.json({ detail: "Username and password are required" }, { status: 400 });
  }

  const backendResponse = await fetch(
    `${BACKEND_URL}/api/v1/auth/login`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email: body.email.trim(),
        password: body.password,
      }),
    }
  );

  const data = await backendResponse.json().catch(() => ({}));

  if (!backendResponse.ok) {
    return NextResponse.json(
      {
        detail: data.detail ?? "Login failed",
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
