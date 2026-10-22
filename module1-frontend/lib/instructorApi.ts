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

  if (Array.isArray(data)) {
    return data;
  }

  return data.items ?? [];
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

export async function fetchSessions(accessToken: string,):
Promise<BackendSession[]> {
  const response = await fetch(
    `${API_BASE}/api/v1/sessions/?limit=100`,
    {
      headers: authHeaders(accessToken),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Unable to load sessions",
    );
  }

  const data = await response.json();

  return data.items ?? [];
}

export type BackendCourse = {
  id: string;
  code: string;
  name: string;
  semester: string;
};

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

export async function fetchCheckins(accessToken: string,): 
  Promise<BackendCheckin[]> {
  const start = new Date();
  start.setHours(0, 0, 0, 0);

  const end = new Date();
  end.setHours(23, 59, 59, 999);

  const params = new URLSearchParams({
    limit: "100",
    start_date: start.toISOString(),
    end_date: end.toISOString(),
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