import type { CheckInResult, GeoCoordinates } from "./types";

export type AttendanceLesson = { session_id: string; class_code: string; title: string; qr_code: string; expires_at: string };
export async function resolveAttendance(code: string, accessToken: string): Promise<AttendanceLesson> {
  const response = await fetch("/api/attendance/resolve", {
    method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` }, body: JSON.stringify({ code }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Unable to find this lesson.");
  return data;
}
export async function submitAttendance(lesson: AttendanceLesson, accessToken: string, frame: string, coordinates: GeoCoordinates): Promise<CheckInResult> {
  let fingerprint = localStorage.getItem("saiv_device_fingerprint");
  if (!fingerprint) { fingerprint = crypto.randomUUID(); localStorage.setItem("saiv_device_fingerprint", fingerprint); }
  const response = await fetch("/api/attendance/checkin", {
    method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ session_id: lesson.session_id, qr_code: lesson.qr_code,
      latitude: coordinates.latitude, longitude: coordinates.longitude, location_accuracy_meters: coordinates.accuracy,
      device_fingerprint: fingerprint, liveness_challenge_response: frame, face_image: frame, liveness_challenge_type: "passive" }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Unable to submit attendance.");
  return { ok: data.status !== "rejected", verificationId: data.id, classCode: lesson.class_code, classTitle: lesson.title,
    status: data.status,
    message: data.status === "approved" ? `Attendance confirmed for ${lesson.title}.`
      : data.status === "flagged" ? "Attendance submitted for tutor review. It has not been approved yet."
        : data.status === "rejected" ? "Attendance verification failed. Contact your tutor for help." : "Attendance submitted and awaiting verification." };
}
