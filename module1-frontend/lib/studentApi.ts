export async function studentRequest<T>(
  path: string,
  token: string | null,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/student${path}`, {
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

/** Fetch every page of a student array endpoint without silently truncating. */
export async function studentList<T extends { id: string }>(path: string, token: string): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  for (let offset = 0; ; ) {
    const page = await studentRequest<T[]>(`${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${offset}`, token);
    for (const item of page) {
      if (seen.has(item.id)) throw new Error("Records changed while loading. Please refresh.");
      seen.add(item.id);
      items.push(item);
    }
    if (page.length < 100) return items;
    offset += page.length;
  }
}
