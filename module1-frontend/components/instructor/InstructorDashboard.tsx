"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import {
  attendanceToCsv,
  attendanceToJson,
  downloadTextFile,
} from "@/lib/exportAttendance";
import type {
  AttendanceRecord,
  InstructorDashboardData,
  InstructorSession,
} from "@/lib/instructorTypes";

const POLL_MS = 30_000;

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
  const [data, setData] = useState<InstructorDashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllFlagged, setShowAllFlagged] = useState(false);
  const [showRecords, setShowRecords] = useState(false);
  const [selectedSession, setSelectedSession] = useState("all");
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [created, setCreated] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/instructor/dashboard", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load dashboard");
      setData((await response.json()) as InstructorDashboardData);
      setLastFetch(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const flaggedPreview = useMemo(() => {
    if (!data) return [];
    return showAllFlagged ? data.flagged : data.flagged.slice(0, 3);
  }, [data, showAllFlagged]);

  const filteredRecords = useMemo(() => {
    if (!data) return [];
    if (selectedSession === "all") return data.records;
    return data.records.filter((row) => row.sessionId === selectedSession);
  }, [data, selectedSession]);

  function exportRecords(format: "csv" | "json") {
    const stamp = new Date().toISOString().slice(0, 10);
    if (format === "csv") {
      downloadTextFile(`attendance-${stamp}.csv`, attendanceToCsv(filteredRecords), "text/csv;charset=utf-8");
      return;
    }
    downloadTextFile(
      `attendance-${stamp}.json`,
      JSON.stringify(attendanceToJson(filteredRecords), null, 2),
      "application/json",
    );
  }

  return (
    <div className="w-full max-w-6xl space-y-4 px-4 py-6 animate-fade-up sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-white/70">Instructor</p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-white">
            Today&apos;s operations
          </h1>
          <p className="mt-1 text-sm text-white/75">
            Live sessions and flagged check-ins first. Exports stay collapsed until you need them.
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

      <div className="grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-7">
          <GlassCard className="h-full p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-xl font-semibold text-white">Today&apos;s sessions</h2>
              <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white">
                {data?.kpis.liveSessions ?? 0} live
              </span>
            </div>
            <ul className="mt-4 space-y-3">
              {(data?.todaySessions ?? []).map((session) => (
                <SessionRow key={session.id} session={session} />
              ))}
            </ul>
            <form
              className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]"
              onSubmit={(e) => {
                e.preventDefault();
                setCreated(newTitle.trim() || "Untitled session");
                setNewTitle("");
              }}
            >
              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="New session title"
                className="rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none placeholder:text-white/40"
              />
              <button type="submit" className="rounded-2xl bg-white/90 px-5 py-3 font-semibold text-sky-950">
                Create
              </button>
            </form>
            {created && <p className="mt-2 text-sm text-emerald-200">Queued: {created}</p>}
          </GlassCard>
        </section>

        <section className="lg:col-span-5">
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
                    <button type="button" className="rounded-lg bg-white/90 px-2.5 py-1 text-xs font-semibold text-sky-950">
                      Approve
                    </button>
                    <button type="button" className="rounded-lg border border-white/30 px-2.5 py-1 text-xs text-white">
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="Today's check-ins" value={String(data?.kpis.todayCheckins ?? "—")} />
        <Kpi label="Flagged pending" value={String(data?.kpis.flaggedPending ?? "—")} />
        <Kpi label="Approval rate" value={data ? `${Math.round(data.kpis.approvalRate * 100)}%` : "—"} />
        <Kpi label="Live sessions" value={String(data?.kpis.liveSessions ?? "—")} />
      </div>

      <details className="group">
        <summary className="cursor-pointer list-none">
          <GlassCard className="p-5">
            <div className="flex items-center justify-between">
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
          </GlassCard>
        </summary>
        <GlassCard className="mt-3 p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm text-white/80">
              Session
              <select
                value={selectedSession}
                onChange={(e) => setSelectedSession(e.target.value)}
                className="ml-2 rounded-xl border border-white/25 bg-sky-950/80 px-3 py-2 text-white"
              >
                <option value="all">All today</option>
                {(data?.todaySessions ?? []).map((session) => (
                  <option key={session.id} value={session.id}>
                    {session.title}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => exportRecords("csv")}
              className="rounded-xl bg-white/90 px-4 py-2 text-sm font-semibold text-sky-950"
            >
              Export CSV
            </button>
            <button
              type="button"
              onClick={() => exportRecords("json")}
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
              <RecordsTable records={filteredRecords} />
            </div>
          )}
        </GlassCard>
      </details>
    </div>
  );
}

function SessionRow({ session }: { session: InstructorSession }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-2xl border border-white/15 bg-white/10 px-4 py-3">
      <div>
        <p className="font-medium text-white">{session.title}</p>
        <p className="text-xs text-white/65">
          {session.courseCode} · {session.checkins}/{session.enrolled} checked in
          {session.flagged ? ` · ${session.flagged} flagged` : ""}
        </p>
      </div>
      <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${statusClass(session.status)}`}>
        {session.status}
      </span>
    </li>
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
