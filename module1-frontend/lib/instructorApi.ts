const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BackendFlaggedCheckin = {
  id: string;
  session_id: string;
  session_name: string;
  student_id: string;
  student_name: string;
  status: "flagged" | "appealed";
  checked_in_at: string;
  risk_score: number;
  risk_factors: {
    type: string;
    severity?: string | null;
    weight: number;
  }[];
  appeal_reason?: string | null;
  appealed_at?: string | null;
};

export type ReviewDecision = "approved" | "rejected";

function authHeaders(accessToken: string) {
  return {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  };
}

async function fetchAllPages<T extends { id: string }>(path: string, accessToken: string, filters = new URLSearchParams()): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  for (let offset = 0; ; ) {
    const params = new URLSearchParams(filters);
    params.set("limit", "100");
    params.set("offset", String(offset));
    const response = await fetch(`${API_BASE}/api/v1${path}?${params}`, {
      headers: authHeaders(accessToken), cache: "no-store", signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail ?? "Unable to load dashboard records");
    }
    const page = await response.json();
    if (!Array.isArray(page.items) || typeof page.total !== "number")
      throw new Error("Invalid paginated response");
    for (const item of page.items) {
      if (seen.has(item.id)) throw new Error("Records changed while loading. Please refresh.");
      seen.add(item.id);
      items.push(item);
    }
    offset += page.items.length;
    if (offset >= page.total) return items;
    if (!page.items.length) throw new Error("Incomplete report; please refresh.");
  }
}

export function attendanceFilters(sessionId = "all"): URLSearchParams {
  if (sessionId !== "all") return new URLSearchParams({ session_id: sessionId });
  // Singapore calendar day, independent of the browser's timezone.
  const local = new Date(Date.now() + 8 * 3600_000);
  local.setUTCHours(0, 0, 0, 0);
  const start = local.getTime() - 8 * 3600_000;
  return new URLSearchParams({ start_date: new Date(start).toISOString(),
    end_date: new Date(start + 24 * 3600_000 - 1).toISOString() });
}

export async function exportAttendance(accessToken: string, format: "csv" | "json", sessionId: string): Promise<string> {
  const params = attendanceFilters(sessionId);
  params.set("format", format);
  const response = await fetch(`${API_BASE}/api/v1/export/checkins?${params}`, {
    headers: authHeaders(accessToken), cache: "no-store", signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) throw new Error("Export failed. Please retry.");
  return response.text();
}

export async function fetchFlaggedCheckins(accessToken: string): Promise<BackendFlaggedCheckin[]> {
  return fetchAllPages<BackendFlaggedCheckin>("/checkins/flagged", accessToken);
}

export async function reviewFlaggedCheckin(
  checkinId: string,
  decision: ReviewDecision,
  accessToken: string,
  reviewNotes?: string,
) {
  const response = await fetch(
    `${API_BASE}/api/v1/checkins/${checkinId}/review`,
    {
      method: "POST",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        status: decision,
        review_notes: reviewNotes ?? null,
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(error?.detail ?? "Unable to review check-in");
  }

  return response.json();
}

export type BackendSession = {
  id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  instructor_id?: string | null;
  name: string;
  session_type?: string;
  status: "scheduled" | "active" | "closed" | "cancelled";
  scheduled_start: string;
  scheduled_end: string;
  checkin_opens_at: string;
  checkin_closes_at: string;
  venue_name?: string | null;
  total_enrolled: number;
  checked_in_count: number;
};

export async function fetchSessions(accessToken: string): Promise<BackendSession[]> {
  return fetchAllPages<BackendSession>("/sessions/", accessToken);
}

export type BackendCourse = {
  id: string;
  code: string;
  name: string;
  semester: string;
};

export async function fetchCourses(accessToken: string): Promise<BackendCourse[]> {
  return fetchAllPages<BackendCourse>("/courses/", accessToken);
}

export async function createBackendSession(
  accessToken: string,
  payload: {
    course_id: string;
    name: string;
    scheduled_start: string;
    scheduled_end: string;
  },
) {
  const response = await fetch(
    `${API_BASE}/api/v1/sessions/`,
    {
      method: "POST",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        ...payload,
        session_type: "lecture",
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Unable to create session");
  }

  return response.json();
}

export type BackendCheckin = {
  id: string;
  session_id: string;
  session_name: string;
  student_id: string;
  student_name: string;
  student_email: string;
  status:
    | "pending"
    | "approved"
    | "flagged"
    | "rejected"
    | "appealed";
  checked_in_at: string;
  distance_from_venue_meters?: number | null;
  risk_score: number;
  liveness_passed?: boolean | null;
};

export async function fetchCheckins(accessToken: string, sessionId = "all"): Promise<BackendCheckin[]> {
  return fetchAllPages<BackendCheckin>("/checkins/", accessToken, attendanceFilters(sessionId));
}

export async function updateBackendSessionStatus(
  accessToken: string,
  sessionId: string,
  status: "active" | "closed",
) {
  const response = await fetch(
    `${API_BASE}/api/v1/sessions/${sessionId}`,
    {
      method: "PATCH",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        status,
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Unable to update session status",
    );
  }

  return response.json();
}

export type BackendAuditLog = {
  id: string;
  user_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  success: boolean;
  timestamp: string;
  details?: string | null;
};

export async function fetchAuditLogs(accessToken: string): Promise<BackendAuditLog[]> {
  return fetchAllPages<BackendAuditLog>("/audit/logs", accessToken);
}
