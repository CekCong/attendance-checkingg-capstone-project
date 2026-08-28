import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { signAccessToken, signRefreshToken, verifyToken } from "@/lib/jwt";
import type { UserRole } from "@/lib/authTypes";

const REFRESH_COOKIE = "refresh_token";

export async function POST() {
  const token = cookies().get(REFRESH_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Missing refresh token" }, { status: 401 });
  }

  try {
    const payload = await verifyToken(token, "refresh");
    const user = {
      id: String(payload.sub),
      email: String(payload.email),
      full_name: String(payload.email).split("@")[0],
      role: payload.role as UserRole,
    };
    const access_token = await signAccessToken(user);
    const refresh_token = await signRefreshToken(user);

    const response = NextResponse.json({
      access_token,
      token_type: "bearer",
    });
    response.cookies.set(REFRESH_COOKIE, refresh_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 7,
    });
    return response;
  } catch {
    return NextResponse.json({ detail: "Invalid refresh token" }, { status: 401 });
  }
}
