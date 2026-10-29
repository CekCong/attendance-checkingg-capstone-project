const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function studentRequest<T>(
  path: string,
  token: string | null,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API}/api/v1${path}`, {
    signal: AbortSignal.timeout(90_000),
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  }).catch(() => {
    throw new Error("Cannot reach the server. Check your connection and refresh attendance history before retrying a check-in.");
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : response.status === 401
          ? "Your session expired. Please sign in again."
          : "The request could not be completed. Please try again.",
    );
  }
  return data as T;
}

export type StudentSession = {
  id: string;
  course_id: string;
  name: string;
  status: string;
  checkin_opens_at: string;
  checkin_closes_at: string;
  qr_code_enabled: boolean;
};
export type StudentProfile = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  camera_consent: boolean;
  geolocation_consent: boolean;
  face_enrolled: boolean;
};
export type Attendance = {
  id: string;
  session_id: string;
  session_name: string;
  course_code: string;
  status: "approved" | "flagged" | "rejected" | "pending" | "appealed";
  checked_in_at: string;
  risk_score: number;
};
export type LivenessTicket = {
  challenge_id: string;
  challenge_type: "blink" | "head_turn" | "smile";
  expires_in: number;
};
export function serverTime(value: string): number {
  return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}
