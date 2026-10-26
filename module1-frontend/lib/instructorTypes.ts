export type SessionStatus = "live" | "scheduled" | "closed";
export type CheckinStatus = "approved" | "flagged" | "pending" | "rejected" | "appealed";

export type InstructorSession = {
  id: string;
  title: string;
  courseCode: string;
  status: SessionStatus;
  enrolled: number;
  checkins: number;
  flagged: number;
};

export type FlaggedCheckin = {
  id: string;
  studentName: string;
  studentEmail: string;
  sessionTitle: string;
  status: "flagged" | "appealed";
  reason: string;
  riskScore: number;
  checkedInAt: string;
};

export type AttendanceRecord = {
  checkinId: string;
  studentId: string;
  studentName: string;
  studentEmail: string;
  sessionId: string;
  sessionName: string;
  sessionDate: string;
  status: CheckinStatus;
  checkedInAt: string;
  riskScore: number;
  livenessScore?: number;
  faceMatchScore?: number;
  latitude?: number;
  longitude?: number;
};

export type AuditLogEntry = {
  id: string;
  userEmail: string;
  action: string;
  resourceType: string;
  resourceId: string;
  success: boolean;
  timestamp: string;
  details?: Record<string, string | number | boolean>;
};

export type InstructorDashboardData = {
  generatedAt: string;
  todaySessions: InstructorSession[];
  flagged: FlaggedCheckin[];
  records: AttendanceRecord[];
  auditLogs: AuditLogEntry[];
  kpis: {
    todayCheckins: number;
    flaggedPending: number;
    approvalRate: number;
    liveSessions: number;
  };
};
