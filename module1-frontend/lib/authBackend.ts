export const AUTH_BACKEND_URL =
  process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function authErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .filter((item) => item && typeof item.msg === "string")
      .map((item) => item.msg);
    if (messages.length) return messages.join(". ");
  }
  return fallback;
}
