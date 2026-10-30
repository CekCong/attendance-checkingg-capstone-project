import { addDays, localInstant, singaporeDate } from "@/lib/calendar";

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

export async function deleteCourseOrLesson(accessToken: string, scope: "course" | "lesson", id: string) {
  const resource = scope === "course" ? "courses" : "sessions";
  const response = await fetch(`${API_BASE}/api/v1/${resource}/${encodeURIComponent(id)}?permanent=true`, {
    method: "DELETE", headers: authHeaders(accessToken),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === "string" ? error.detail : "Unable to delete. Please try again.");
  }
}

export async function fetchFlaggedCheckins(accessToken: string,): 
Promise<BackendFlaggedCheckin[]> {
  const response = await fetch(
    `${API_BASE}/api/v1/checkins/flagged`,
    {
      headers: authHeaders(accessToken),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Unable to load flagged check-ins",
    );
  }

  const data = await response.json();

  return Array.isArray(data)
    ? data
    : data.items ?? [];
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
  series_id?: string | null;
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

export async function fetchSessions(
  accessToken: string,
  range?: { start: string; end: string },
): Promise<BackendSession[]> {
  const result: BackendSession[] = [];
  let offset = 0;
  while (true) {
    const params = new URLSearchParams({ limit: "100", offset: String(offset) });
    if (range) { params.set("overlap_start", range.start); params.set("end_date", range.end); }
    const response = await fetch(`${API_BASE}/api/v1/sessions/?${params}`, {
      headers: authHeaders(accessToken), cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load lessons");
    const items = data.items ?? [];
    result.push(...items);
    offset += items.length;
    if (!items.length || offset >= data.total) return result;
  }
}

export type LessonPayload = {
  course_id: string;
  name: string;
  session_type: "lecture" | "tutorial" | "lab" | "exam";
  venue_name?: string;
};
export type RecurringLessonPayload = LessonPayload & {
  request_id: string;
  start_date: string;
  end_date: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: "Asia/Singapore";
};
export async function createRecurringLessons(accessToken: string, payload: RecurringLessonPayload): Promise<{ count: number; series_id: string }> {
  const response = await fetch(`${API_BASE}/api/v1/sessions/recurring`, {
    method: "POST", headers: authHeaders(accessToken), body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail)
      ? data.detail.map((item: { msg: string }) => item.msg).join(". ") : "Unable to schedule lessons.";
    throw new Error(detail);
  }
  return data;
}

export type BackendCourse = {
  id: string;
  code: string;
  name: string;
  semester: string;
};

export async function createBackendCourse(
  accessToken: string,
  payload: { code: string; name: string; semester: string },
): Promise<BackendCourse> {
  const response = await fetch(`${API_BASE}/api/v1/courses/`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : "Unable to create course. Check the course details and try again.";
    throw new Error(detail);
  }
  return data;
}

export async function fetchCourses(accessToken: string):
Promise<BackendCourse[]> {
  const response = await fetch(
    `${API_BASE}/api/v1/courses/?limit=100`,
    {
      headers: authHeaders(accessToken),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Unable to load courses");
  }

  const data = await response.json();
  return data.items ?? [];
}

export async function createBackendSession(
  accessToken: string,
  payload: {
    course_id: string;
    name: string;
    scheduled_start: string;
    scheduled_end: string;
    session_type?: LessonPayload["session_type"];
    venue_name?: string;
  },
) {
  const response = await fetch(
    `${API_BASE}/api/v1/sessions/`,
    {
      method: "POST",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        ...payload,
        session_type: payload.session_type ?? "lecture",
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = typeof error?.detail === "string" ? error.detail : Array.isArray(error?.detail)
      ? error.detail.map((item: { msg: string }) => item.msg).join(". ") : "Unable to create lesson.";
    throw new Error(detail);
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

export async function fetchCheckins(accessToken: string,): 
  Promise<BackendCheckin[]> {
  const today = singaporeDate();
  const start = localInstant(today);
  const end = new Date(new Date(localInstant(addDays(today, 1))).getTime() - 1).toISOString();

  const params = new URLSearchParams({
    limit: "100",
    start_date: start,
    end_date: end,
  });

  const response = await fetch(
    `${API_BASE}/api/v1/checkins/?${params.toString()}`,
    {
      headers: authHeaders(accessToken),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Unable to load attendance records",
    );
  }

  const data = await response.json();

  return data.items ?? [];
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

export async function fetchAuditLogs(accessToken: string,): 
Promise<BackendAuditLog[]> {
  const response = await fetch(
    `${API_BASE}/api/v1/audit/logs?limit=100`,
    {
      headers: authHeaders(accessToken),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Unable to load audit logs",
    );
  }

  const data = await response.json();

  return data.items ?? [];
}
