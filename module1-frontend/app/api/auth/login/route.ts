import { NextResponse } from "next/server";
import { signAccessToken, signRefreshToken, stubUser } from "@/lib/jwt";
import { isInstructorApp } from "@/lib/appSurface";

const REFRESH_COOKIE = "refresh_token";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    email?: string;
    password?: string;
  };

  if (!body.email?.trim() || !body.password) {
    return NextResponse.json({ detail: "Username and password are required" }, { status: 400 });
  }

  const user = stubUser(body.email, isInstructorApp() ? "instructor" : "student");
  const access_token = await signAccessToken(user);
  const refresh_token = await signRefreshToken(user);

  const response = NextResponse.json({
    access_token,
    token_type: "bearer",
    user,
  });

  response.cookies.set(REFRESH_COOKIE, refresh_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });

  return response;
}
