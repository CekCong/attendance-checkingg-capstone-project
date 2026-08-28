import type { CheckInPayload, CheckInResult } from "./types";
import { lookupClass } from "./classes";

/**
 * Mock POST /api/attendance/check-in
 * Location and live camera capture are skipped in this stub.
 */
export async function submitCheckIn(
  payload: CheckInPayload,
): Promise<CheckInResult> {
  await new Promise((resolve) => setTimeout(resolve, 900));

  if (!payload.classCode.trim()) {
    return {
      ok: false,
      message: "Missing class code. Return to the dashboard and join a session.",
    };
  }

  if (!payload.frameBase64.startsWith("data:image/")) {
    return {
      ok: false,
      message: "Invalid frame payload. Please retry the liveness challenge.",
    };
  }

  const known = lookupClass(payload.classCode);
  const verificationId = `CHK-${Date.now().toString(36).toUpperCase()}`;

  return {
    ok: true,
    verificationId,
    classCode: known?.code ?? payload.classCode,
    classTitle: known?.title ?? payload.classCode,
    message: `Attendance verified for ${known?.title ?? payload.classCode}.`,
  };
}
