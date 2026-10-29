import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { isInstructorApp } from "./appSurface";

const REFRESH_COOKIE = "refresh_token";
// Server-only address: Docker uses http://backend:8000, browsers never see it.
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

export async function forwardAuth(
  request: Request,
  action: "login" | "refresh" | "logout" | "register",
) {
  const origin = request.headers.get("origin");
  const url = new URL(request.url);
  // Next may normalize request.url to its container address. Host retains the
  // browser-facing port; configure APP_ORIGIN behind a TLS-terminating ingress.
  const expectedOrigin =
    process.env.APP_ORIGIN ||
    `${url.protocol}//${request.headers.get("host") ?? url.host}`;
  if (origin && origin !== expectedOrigin) {
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 },
    );
  }

  const refreshToken = cookies().get(REFRESH_COOKIE)?.value;
  let body: Record<string, unknown> = {};
  if (action === "login" || action === "register") {
    const input = await request.json().catch(() => null);
    if (
      typeof input?.email !== "string" ||
      typeof input?.password !== "string" ||
      !input.email.trim() ||
      !input.password
    ) {
      return NextResponse.json(
        { detail: "Email and password are required" },
        { status: 400 },
      );
    }
    body = { email: input.email.trim(), password: input.password };
    if (action === "register") {
      if (
        isInstructorApp() ||
        typeof input.full_name !== "string" ||
        !input.full_name.trim()
      ) {
        return NextResponse.json(
          { detail: "A name is required for student registration" },
          { status: 400 },
        );
      }
      body = { ...body, full_name: input.full_name.trim(), role: "student" };
    }
  } else if (action === "refresh") {
    if (!refreshToken) {
      return NextResponse.json(
        { detail: "Missing refresh token" },
        { status: 401 },
      );
    }
    body = { refresh_token: refreshToken };
  }

  let response: NextResponse;
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (action === "logout") {
      const authorization = request.headers.get("authorization");
      if (authorization) headers.Authorization = authorization;
    }
    const upstream = await fetch(`${BACKEND_URL}/api/v1/auth/${action}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    const data = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      response = NextResponse.json(
        { detail: data.detail ?? "Authentication failed" },
        { status: upstream.status },
      );
      for (const name of ["retry-after", "x-ratelimit-remaining"]) {
        const value = upstream.headers.get(name);
        if (value) response.headers.set(name, value);
      }
    } else if (action === "register") {
      response = NextResponse.json(data, { status: upstream.status });
    } else if (
      action !== "logout" &&
      isInstructorApp() &&
      !["instructor", "admin"].includes(data.user?.role)
    ) {
      response = NextResponse.json(
        { detail: "Instructor access required" },
        { status: 403 },
      );
    } else {
      response = NextResponse.json(
        action === "logout"
          ? { ok: true }
          : {
              access_token: data.access_token,
              token_type: data.token_type ?? "bearer",
              user: data.user,
            },
      );
      if (action !== "logout" && data.refresh_token) {
        response.cookies.set(REFRESH_COOKIE, data.refresh_token, {
          httpOnly: true,
          secure: process.env.NODE_ENV === "production",
          sameSite: "lax",
          path: "/",
          maxAge: 7 * 24 * 60 * 60,
        });
      }
    }
  } catch {
    response = NextResponse.json(
      { detail: "Authentication service unavailable" },
      { status: 502 },
    );
  }
  response.headers.set("Cache-Control", "no-store");
  if (
    action === "logout" ||
    (action === "refresh" && [401, 403].includes(response.status))
  ) {
    response.cookies.set(REFRESH_COOKIE, "", {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
  }
  return response;
}
