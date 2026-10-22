import type { AttendanceRecord } from "./instructorTypes";

const CSV_COLUMNS = [
  "checkin_id",
  "student_id",
  "student_name",
  "student_email",
  "session_id",
  "session_date",
  "session_name",
  "status",
  "checked_in_at",
  "risk_score",
  "liveness_score",
  "face_match_score",
  "latitude",
  "longitude",
] as const;

function csvEscape(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function attendanceToCsv(records: AttendanceRecord[]): string {
  const header = CSV_COLUMNS.join(",");
  const rows = records.map((row) =>
    [
      row.checkinId,
      row.studentId,
      row.studentName,
      row.studentEmail,
      row.sessionId,
      row.sessionDate,
      row.sessionName,
      row.status,
      row.checkedInAt,
      row.riskScore,
      row.livenessScore,
      row.faceMatchScore,
      row.latitude,
      row.longitude,
    ]
      .map(csvEscape)
      .join(","),
  );
  return [header, ...rows].join("\n");
}

export function attendanceToJson(records: AttendanceRecord[]) {
  return {
    exported_at: new Date().toISOString(),
    total: records.length,
    records,
  };
}

export function downloadTextFile(filename: string, contents: string, mime: string) {
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
