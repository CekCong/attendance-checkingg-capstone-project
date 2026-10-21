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