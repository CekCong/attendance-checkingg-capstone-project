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
  livenessScore: number;
  faceMatchScore: number;
  latitude: number;
  longitude: number;
};

export type InstructorDashboardData = {
  generatedAt: string;
  todaySessions: InstructorSession[];
  flagged: FlaggedCheckin[];
  records: AttendanceRecord[];
  kpis: {
    todayCheckins: number;
    flaggedPending: number;
    approvalRate: number;
    liveSessions: number;
  };
};
