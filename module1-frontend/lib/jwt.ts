import { SignJWT, jwtVerify } from "jose";
import type { AuthUser, UserRole } from "./authTypes";

type TokenUser = Pick<AuthUser, "id" | "email" | "role">;

const ACCESS_TTL = "1h";
const REFRESH_TTL = "7d";

function secret() {
  return new TextEncoder().encode(
    process.env.JWT_SECRET || process.env.SECRET_KEY || "saiv-dev-secret-change-me",
  );
}

export async function signAccessToken(user: TokenUser): Promise<string> {
  return new SignJWT({
    sub: user.id,
    email: user.email,
    role: user.role,
    type: "access",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(ACCESS_TTL)
    .sign(secret());
}

export async function signRefreshToken(user: TokenUser): Promise<string> {
  return new SignJWT({
    sub: user.id,
    email: user.email,
    role: user.role,
    type: "refresh",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(REFRESH_TTL)
    .sign(secret());
}

export async function verifyToken(token: string, expectedType: "access" | "refresh") {
  const { payload } = await jwtVerify(token, secret());
  if (payload.type !== expectedType) {
    throw new Error("Invalid token type");
  }
  return payload;
}

export function stubUser(email: string, role: UserRole): AuthUser {
  const normalized = email.trim() || "demo@saiv.local";
  return {
    id: crypto.randomUUID(),
    email: normalized.includes("@") ? normalized : `${normalized}@saiv.local`,
    username: normalized.split("@")[0],
    full_name: normalized.split("@")[0].replace(/[._]/g, " "),
    role,
    language: "en",
  };
}
