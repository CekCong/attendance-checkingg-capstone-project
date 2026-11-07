"use client";

import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import {
  downloadTextFile,
} from "@/lib/exportAttendance";
import type {
  AttendanceRecord,
  InstructorDashboardData,
} from "@/lib/instructorTypes";
import { useAuth } from "@/components/auth/AuthProvider";
import { AttendancePanel } from "@/components/instructor/AttendancePanel";
import { CourseManager } from "@/components/instructor/CourseManager";
import { SessionCalendar } from "@/components/instructor/SessionCalendar";
import type { Deletion } from "@/components/instructor/DeleteCourseControl";
import { addDays, localInstant, parseSessionDate, singaporeDate } from "@/lib/calendar";
import {
  fetchFlaggedCheckins,
  reviewFlaggedCheckin,
  fetchSessions,
  fetchCourses,
  fetchCheckins,
  fetchAuditLogs,
  exportAttendance,
  type BackendCheckin,
  type BackendCourse,
  type BackendSession,
} from "@/lib/instructorApi";

const POLL_MS = 30_000;
function attendanceRecord(checkin: BackendCheckin): AttendanceRecord {
  return { checkinId: checkin.id, studentId: checkin.student_id,
    studentName: checkin.student_name, studentEmail: checkin.student_email,
    sessionId: checkin.session_id, sessionName: checkin.session_name,
    sessionDate: checkin.checked_in_at.slice(0, 10), status: checkin.status,
    checkedInAt: checkin.checked_in_at, riskScore: checkin.risk_score };
}

function formatTime(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function statusClass(status: string) {
  if (status === "live") return "bg-emerald-300/90 text-emerald-950";
  if (status === "flagged" || status === "appealed") return "bg-amber-300/90 text-amber-950";
  if (status === "approved") return "bg-emerald-200/80 text-emerald-950";
  if (status === "rejected") return "bg-rose-300/90 text-rose-950";
  return "bg-white/20 text-white";
}

export function InstructorDashboard() {
  const { accessToken } = useAuth();

  const [data, setData] = useState<InstructorDashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllFlagged, setShowAllFlagged] = useState(false);
  const [showRecords, setShowRecords] = useState(false);
  const [selectedSession, setSelectedSession] = useState("all");
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [auditSearch, setAuditSearch] = useState("");
  const [auditAction, setAuditAction] = useState("all");
  const [auditResult, setAuditResult] = useState("all");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [calendarLesson, setCalendarLesson] = useState<BackendSession | null>(null);
  const [calendarRevision, setCalendarRevision] = useState(0);
  const [courses, setCourses] = useState<BackendCourse[]>([]);
  const [reportSessions, setReportSessions] = useState<BackendSession[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");

  function handleDeleted({ courseId, lessonId }: Deletion) {
    if (!lessonId) {
      setCourses((current) => current.filter((course) => course.id !== courseId));
      setSelectedCourseId((current) => current === courseId ? "" : current);
    }
    setCalendarLesson((current) => current && (lessonId ? current.id === lessonId : current.course_id === courseId) ? null : current);
    setSelectedSession("all");
    setCalendarRevision((value) => value + 1);
    void load();
  }

  const [sessionRecords, setSessionRecords] = useState<AttendanceRecord[]>([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const loadGeneration = useRef(0);
  useEffect(() => {
    let active = true;
    setSessionRecords([]);
    if (!accessToken || selectedSession === "all") { setReportLoading(false); return; }
    setReportLoading(true);
    fetchCheckins(accessToken, selectedSession).then((items) => {
      if (active) setSessionRecords(items.map(attendanceRecord));
    }).catch((e) => { if (active) setError(e.message); })
      .finally(() => { if (active) setReportLoading(false); });
    return () => { active = false; };
  }, [accessToken, selectedSession, lastFetch]);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    if (!accessToken) {
      setData(null);
      setCourses([]);
      setReportSessions([]);
      return;
    }
    try {
      const dashboard: InstructorDashboardData = {
        generatedAt: new Date().toISOString(),
        todaySessions: [],
        flagged: [],
        records: [],
        auditLogs: [],
        kpis: {
          todayCheckins: 0,
          flaggedPending: 0,
          approvalRate: 0,
          liveSessions: 0,
        },
      };

      if (accessToken) {
        const [backendFlagged, backendSessions, backendCourses, backendCheckins, backendAuditLogs,] =
          await Promise.all([
            fetchFlaggedCheckins(accessToken),
            fetchSessions(accessToken),
            fetchCourses(accessToken),
            fetchCheckins(accessToken),
            fetchAuditLogs(accessToken),
          ]);

          if (generation !== loadGeneration.current) return;
          setCourses(backendCourses)
          setReportSessions(backendSessions);

        dashboard.flagged = backendFlagged.map((item) => ({
          id: item.id,
          studentName: item.student_name,
          studentEmail: "",
          sessionTitle: item.session_name,
          status: item.status,
          reason:
            item.appeal_reason ||
            item.risk_factors
              .map((factor) => factor.type)
              .join(", ") ||
            "Risk review",
          riskScore: item.risk_score,
          checkedInAt: item.checked_in_at,
        }));

        const start = new Date(localInstant(singaporeDate())).getTime();
        const end = new Date(localInstant(addDays(singaporeDate(), 1))).getTime();
        dashboard.todaySessions = backendSessions.filter((session) =>
          parseSessionDate(session.scheduled_start).getTime() < end && parseSessionDate(session.scheduled_end).getTime() > start).map(
          (session) => ({
            id: session.id,
            title: session.name,
            courseCode: session.course_code,
            status:
              session.status === "active"
                ? "live"
                : session.status === "cancelled"
                  ? "closed"
                  : session.status,
            enrolled: session.total_enrolled,
            checkins: session.checked_in_count,

            flagged: backendFlagged.filter(
              (item) => item.session_id === session.id,
            ).length,
          }),
        );

        dashboard.records = backendCheckins.map(attendanceRecord);

        dashboard.auditLogs = backendAuditLogs.map((log) => ({
          id: log.id,
          userEmail: log.user_id ?? "System",

          action: log.action,
          resourceType: log.resource_type ?? "",
          resourceId: log.resource_id ?? "",
          success: log.success,
          timestamp: log.timestamp,

          details: {
            message: log.details ?? "",
          },
        }));

        dashboard.kpis.flaggedPending =
          dashboard.flagged.length;

        dashboard.kpis.liveSessions =
          backendSessions.filter(
            (session) => session.status === "active",
          ).length;

        dashboard.kpis.todayCheckins = backendCheckins.length;

        const approvedCount = backendCheckins.filter(
          (checkin) => checkin.status === "approved",
        ).length;

        dashboard.kpis.approvalRate =
          backendCheckins.length > 0
            ? approvedCount / backendCheckins.length
            : 0;
      }

      setData(dashboard);
      setLastFetch(new Date());
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Refresh failed",
      );
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const flaggedPreview = useMemo(() => {
    if (!data) return [];
    return showAllFlagged ? data.flagged : data.flagged.slice(0, 3);
  }, [data, showAllFlagged]);

  const filteredRecords = selectedSession === "all" ? data?.records ?? [] : sessionRecords;

  const auditActions = useMemo(() => {
    if (!data) return [];

    return Array.from(
      new Set(data.auditLogs.map((log) => log.action)),
    ).sort();
  }, [data]);

  const filteredAuditLogs = useMemo(() => {
    if (!data) return [];

    const search = auditSearch.trim().toLowerCase();

    return data.auditLogs.filter((log) => {
      const matchesSearch =
        !search ||
        log.userEmail.toLowerCase().includes(search) ||
        log.action.toLowerCase().includes(search) ||
        log.resourceType.toLowerCase().includes(search) ||
        log.resourceId.toLowerCase().includes(search);

      const matchesAction =
        auditAction === "all" || log.action === auditAction;

      const matchesResult =
        auditResult === "all" ||
        (auditResult === "success" && log.success) ||
        (auditResult === "failed" && !log.success);

      return matchesSearch && matchesAction && matchesResult;
    });
  }, [data, auditSearch, auditAction, auditResult]);

  const attendanceAnalytics = useMemo(() => {
    if (!data) {
      return {
        approved: 0,
        flagged: 0,
        rejected: 0,
        total: 0,
      };
    }

    const approved = data.records.filter(
      (record) => record.status === "approved").length;

    const flagged = data.records.filter(
      (record) => record.status === "flagged").length;

    const rejected = data.records.filter(
      (record) => record.status === "rejected").length;

    return {
      approved,
      flagged,
      rejected,
      total: data.records.length
    };
  }, [data]);

  async function exportRecords(format: "csv" | "json") {
    if (!accessToken) return;
    setExporting(true);
    try {
      const contents = await exportAttendance(accessToken, format, selectedSession);
      downloadTextFile(`attendance.${format}`, contents, format === "csv" ? "text/csv;charset=utf-8" : "application/json");
      await load();
    } catch (error) { setError(error instanceof Error ? error.message : "Export failed"); }
    finally { setExporting(false); }
  }

  async function reviewCheckin(
    checkinId: string,
    decision: "approved" | "rejected",
  ) {
    if (!accessToken) {
      setError("You must be logged in to review check-ins.");
      return;
    }

    try {
      setReviewingId(checkinId);
      setError(null);

      await reviewFlaggedCheckin(
        checkinId,
        decision,
        accessToken,
      );

      await load();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not review check-in",
      );
    } finally {
      setReviewingId(null);
    }   
  };


  return (
    <div className="w-full max-w-[1600px] space-y-4 px-4 py-6 animate-fade-up sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-white/70">Instructor</p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-white">
            Your teaching week
          </h1>
          <p className="mt-1 text-sm text-white/75">
            Plan your lessons, manage attendance, and keep your week in view.
          </p>
        </div>
        <div className="text-right text-xs text-white/60">
          <p>
            Auto-refresh every 30s
            <span className="ml-2 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-300" />
          </p>
          <p>{lastFetch ? `Updated ${formatTime(lastFetch.toISOString())}` : "Loading…"}</p>
          <button type="button" onClick={() => void load()} className="mt-1 text-white/80 hover:underline">
            Refresh now
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-xl bg-rose-500/20 px-3 py-2 text-sm text-rose-100">{error}</p>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)]">
      <div className="min-w-0 space-y-4 lg:sticky lg:top-4">
      <details className="rounded-2xl border border-white/20 bg-white/10">
      <summary className="cursor-pointer px-5 py-3 text-sm font-semibold text-white">Courses, students & semesters</summary>
      <CourseManager
        accessToken={accessToken}
        courses={courses}
        selectedCourseId={selectedCourseId}
        onDeleted={handleDeleted}
        onSelect={setSelectedCourseId}
        onCreated={(course) => {
          setCourses((current) => [course, ...current.filter((item) => item.id !== course.id)]);
          setSelectedCourseId(course.id);
        }}
      />

      </details>
      <SessionCalendar accessToken={accessToken} courses={courses} courseId={selectedCourseId}
        onCourseChange={setSelectedCourseId} onChanged={load} onSelectLesson={setCalendarLesson} refreshKey={calendarRevision} />
      </div>
      <aside className="min-w-0 space-y-4" aria-label="Attendance tools and summaries">
        <AttendancePanel lesson={calendarLesson} accessToken={accessToken} onDeleted={handleDeleted} onChanged={(lesson) => { setCalendarLesson(lesson); setCalendarRevision((value) => value + 1); void load(); }} />

      <div className="grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-12">
          <GlassCard className="h-full p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-xl font-semibold text-white">Flagged check-ins</h2>
              <span className="rounded-full bg-amber-300/90 px-3 py-1 text-xs font-semibold text-amber-950">
                {data?.kpis.flaggedPending ?? 0} need review
              </span>
            </div>
            <ul className="mt-4 space-y-3">
              {flaggedPreview.map((item) => (
                <li key={item.id} className="rounded-2xl border border-white/15 bg-white/10 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-white">{item.studentName}</p>
                      <p className="text-xs text-white/65">{item.sessionTitle}</p>
                      <p className="mt-1 text-xs uppercase tracking-wide text-amber-200">
                        {item.reason} · risk {item.riskScore.toFixed(2)}
                      </p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusClass(item.status)}`}>
                      {item.status}
                    </span>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <button type="button" onClick={() => void reviewCheckin(item.id, "approved")} disabled={reviewingId === item.id} className="rounded-lg bg-white/90 px-2.5 py-1 text-xs font-semibold text-sky-950">
                      Approve
                    </button>
                    <button type="button" onClick={() => void reviewCheckin(item.id, "rejected")} disabled={reviewingId === item.id} className="rounded-lg border border-white/30 px-2.5 py-1 text-xs text-white">
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            {(data?.flagged.length ?? 0) > 3 && (
              <button
                type="button"
                onClick={() => setShowAllFlagged((open) => !open)}
                className="mt-4 text-sm font-medium text-white/80 hover:text-white"
              >
                {showAllFlagged ? "Show fewer" : `Show all ${data?.flagged.length} flagged`}
              </button>
            )}
          </GlassCard>
        </section>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2">
        <Kpi label="Today's check-ins" value={String(data?.kpis.todayCheckins ?? "—")} />
        <Kpi label="Flagged pending" value={String(data?.kpis.flaggedPending ?? "—")} />
        <Kpi label="Approval rate" value={data ? `${Math.round(data.kpis.approvalRate * 100)}%` : "—"} />
        <Kpi label="Live sessions" value={String(data?.kpis.liveSessions ?? "—")} />
      </div>
      <GlassCard className="p-5 sm:p-6">
        <div className="mb-5">
          <h2 className="font-display text-xl font-semibold text-white">
            Attendance analytics
          </h2>

          <p className="mt-1 text-sm text-white/70">
            Live breakdown of today&apos;s attendance records.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">

          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-sm text-white/60">Approved</p>

            <p className="mt-2 text-3xl font-semibold text-emerald-200">
              {attendanceAnalytics.approved}
            </p>

            <p className="mt-1 text-xs text-white/50">
              {attendanceAnalytics.total > 0
                ? Math.round(
                    (attendanceAnalytics.approved /
                      attendanceAnalytics.total) *
                      100,
                  )
                : 0}
              % of records
            </p>
          </div>

          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-sm text-white/60">Flagged</p>

            <p className="mt-2 text-3xl font-semibold text-amber-200">
              {attendanceAnalytics.flagged}
            </p>

            <p className="mt-1 text-xs text-white/50">
              Requires instructor review
            </p>
          </div>

          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-sm text-white/60">Rejected</p>

            <p className="mt-2 text-3xl font-semibold text-rose-200">
              {attendanceAnalytics.rejected}
            </p>

            <p className="mt-1 text-xs text-white/50">
              Rejected attendance attempts
            </p>
          </div>
        </div>
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">
                Attendance status breakdown
              </h3>

              <p className="text-xs text-white/55">
                Distribution of today&apos;s attendance records
              </p>
            </div>

            <p className="text-xs text-white/55">
              {attendanceAnalytics.total} total
            </p>
          </div>

          {attendanceAnalytics.total === 0 ? (
            <p className="rounded-2xl bg-white/10 px-4 py-6 text-center text-sm text-white/60">
              No attendance records for today.
            </p>
          ) : (
            <div className="space-y-4">

              <AttendanceBar
                label="Approved"
                value={attendanceAnalytics.approved}
                total={attendanceAnalytics.total}
                barClass="bg-emerald-300"
              />

              <AttendanceBar
                label="Flagged"
                value={attendanceAnalytics.flagged}
                total={attendanceAnalytics.total}
                barClass="bg-amber-300"
              />

              <AttendanceBar
                label="Rejected"
                value={attendanceAnalytics.rejected}
                total={attendanceAnalytics.total}
                barClass="bg-rose-300"
              />

            </div>
          )}
        </div>
      </GlassCard>
      <GlassCard className="p-5 sm:p-6">
        <div className="mb-5">
          <h2 className="font-display text-xl font-semibold text-white">
            Session attendance progress
          </h2>

          <p className="mt-1 text-sm text-white/70">
            Check-in progress for today&apos;s sessions.
          </p>
        </div>

        <div className="space-y-4">
          {(data?.todaySessions ?? []).map((session) => {
            const percentage =
              session.enrolled > 0
                ? Math.min(
                    100,
                    Math.round(
                      (session.checkins / session.enrolled) * 100,
                    ),
                  )
                : 0;

            return (
              <div
                key={session.id}
                className="rounded-2xl bg-white/10 p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-white">
                      {session.title}
                    </p>

                    <p className="text-xs text-white/60">
                      {session.courseCode}
                    </p>
                  </div>

                  <p className="text-sm font-semibold text-white">
                    {percentage}%
                  </p>
                </div>

                <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/15">
                  <div
                    className="h-full rounded-full bg-emerald-300"
                    style={{ width: `${percentage}%` }}
                  />
                </div>

                <div className="mt-2 flex justify-between text-xs text-white/60">
                  <span>
                    {session.checkins}/{session.enrolled} checked in
                  </span>

                  <span>
                    {session.flagged} flagged
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </GlassCard>
      <GlassCard>
      <details className="group">
        <summary className="cursor-pointer list-none p-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-white sm:p-6 [&::-webkit-details-marker]:hidden">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="font-display text-xl font-semibold text-white">
                  Attendance records & export
                </h2>
                <p className="mt-1 text-sm text-white/70">
                  Student details, status, and risk scores. Export CSV or JSON for grading.
                </p>
              </div>
              <span className="text-sm text-white/60 group-open:hidden">Show</span>
              <span className="hidden text-sm text-white/60 group-open:inline">Hide</span>
            </div>
        </summary>
        <div className="border-t border-white/15 p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm text-white/80">
              Session
              <select
                aria-label="Attendance session"
                value={selectedSession}
                onChange={(e) => setSelectedSession(e.target.value)}
                className="ml-2 rounded-xl border border-white/25 bg-sky-950/80 px-3 py-2 text-white"
              >
                <option value="all">All today (Singapore)</option>
                {reportSessions.map((session) => (
                  <option key={session.id} value={session.id}>
                    {session.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={exporting}
              onClick={() => void exportRecords("csv")}
              className="rounded-xl bg-white/90 px-4 py-2 text-sm font-semibold text-sky-950"
            >
              Export CSV
            </button>
            <button
              type="button"
              disabled={exporting}
              onClick={() => void exportRecords("json")}
              className="rounded-xl border border-white/30 px-4 py-2 text-sm font-semibold text-white"
            >
              Export JSON
            </button>
            <button
              type="button"
              onClick={() => setShowRecords((open) => !open)}
              className="text-sm text-white/75 hover:text-white"
            >
              {showRecords ? "Hide table" : "Preview table"}
            </button>
          </div>
          {showRecords && (
            <div className="mt-4 overflow-x-auto">
              {reportLoading ? <p>Loading report…</p> : <RecordsTable records={filteredRecords} />}
            </div>
          )}
        </div>
      </details>
      </GlassCard>
      <GlassCard>
      <details className="group">
        <summary className="cursor-pointer list-none p-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-white sm:p-6 [&::-webkit-details-marker]:hidden">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="font-display text-xl font-semibold text-white">
                  Audit log explorer
                </h2>
                <p className="mt-1 text-sm text-white/70">
                  Review security and attendance events recorded by the system.
                </p>
              </div>

              <span className="text-sm text-white/60 group-open:hidden">
                Show
              </span>

              <span className="hidden text-sm text-white/60 group-open:inline">
                Hide
              </span>
            </div>
        </summary>

        <div className="border-t border-white/15 p-5 sm:p-6">

          <div className="flex flex-wrap gap-3">

            <input
              value={auditSearch}
              onChange={(e) => setAuditSearch(e.target.value)}
              placeholder="Search logs..."
              className="min-w-[220px] flex-1 rounded-xl border border-white/25 bg-white/10 px-3 py-2 text-sm text-white outline-none placeholder:text-white/40"
            />

            <select
              value={auditAction}
              onChange={(e) => setAuditAction(e.target.value)}
              className="rounded-xl border border-white/25 bg-sky-950/80 px-3 py-2 text-sm text-white"
            >
              <option value="all">All actions</option>

              {auditActions.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>

            <select
              value={auditResult}
              onChange={(e) => setAuditResult(e.target.value)}
              className="rounded-xl border border-white/25 bg-sky-950/80 px-3 py-2 text-sm text-white"
            >
              <option value="all">All results</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
            </select>

          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm text-white/85">

              <thead className="text-xs uppercase tracking-wide text-white/55">
                <tr>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">User</th>
                  <th className="py-2 pr-4">Action</th>
                  <th className="py-2 pr-4">Resource</th>
                  <th className="py-2">Result</th>
                </tr>
              </thead>

              <tbody>
                {filteredAuditLogs.map((log) => (
                  <tr key={log.id} className="border-t border-white/10">

                    <td className="whitespace-nowrap py-3 pr-4">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>

                    <td className="py-3 pr-4">
                      {log.userEmail}
                    </td>

                    <td className="py-3 pr-4 font-medium text-white">
                      {log.action}
                    </td>

                    <td className="py-3 pr-4">
                      <p>{log.resourceType}</p>
                      <p className="text-xs text-white/50">
                        {log.resourceId}
                      </p>
                    </td>

                    <td className="py-3">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-semibold ${
                          log.success
                            ? "bg-emerald-300/90 text-emerald-950"
                            : "bg-rose-300/90 text-rose-950"
                        }`}
                      >
                        {log.success ? "SUCCESS" : "FAILED"}
                      </span>
                    </td>

                  </tr>
                ))}
              </tbody>

            </table>

            {filteredAuditLogs.length === 0 && (
              <p className="py-6 text-center text-sm text-white/60">
                No audit logs match these filters.
              </p>
            )}
          </div>

        </div>
      </details>
      </GlassCard>
      </aside>
      </div>
    </div>
  );
}


function AttendanceBar({
  label,
  value,
  total,
  barClass,
}: {
  label: string;
  value: number;
  total: number;
  barClass: string;
}) {
  const percentage =
    total > 0
      ? Math.round((value / total) * 100)
      : 0;

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-sm">
        <span className="text-white/75">
          {label}
        </span>

        <span className="font-medium text-white">
          {value} ({percentage}%)
        </span>
      </div>

      <div className="h-3 overflow-hidden rounded-full bg-white/15">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barClass}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <GlassCard className="p-4">
      <p className="text-xs uppercase tracking-wide text-white/60">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold text-white">{value}</p>
    </GlassCard>
  );
}

function RecordsTable({ records }: { records: AttendanceRecord[] }) {
  if (records.length === 0) {
    return <p className="text-sm text-white/60">No records for this filter.</p>;
  }
  return (
    <table className="min-w-full text-left text-sm text-white/85">
      <thead className="text-xs uppercase tracking-wide text-white/55">
        <tr>
          <th className="py-2 pr-3">Student</th>
          <th className="py-2 pr-3">Session</th>
          <th className="py-2 pr-3">Status</th>
          <th className="py-2 pr-3">Risk</th>
          <th className="py-2">Checked in</th>
        </tr>
      </thead>
      <tbody>
        {records.map((row) => (
          <tr key={row.checkinId} className="border-t border-white/10">
            <td className="py-2 pr-3">
              <p className="text-white">{row.studentName}</p>
              <p className="text-xs text-white/55">{row.studentEmail}</p>
            </td>
            <td className="py-2 pr-3">{row.sessionName}</td>
            <td className="py-2 pr-3">
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusClass(row.status)}`}>
                {row.status}
              </span>
            </td>
            <td className="py-2 pr-3">{row.riskScore.toFixed(2)}</td>
            <td className="py-2">{formatTime(row.checkedInAt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
