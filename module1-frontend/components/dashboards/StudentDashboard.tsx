"use client";

import { useEffect, useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { useAuth } from "@/components/auth/AuthProvider";
import { resolveAttendance, type AttendanceLesson } from "@/lib/studentAttendance";
import { loadLessonHistory } from "@/lib/attendanceHistory";
import type { LessonHistoryItem } from "@/lib/types";

type StudentDashboardProps = {
  email: string;
  historyVersion: number;
  onStartCheckIn: (lesson: AttendanceLesson) => void;
};

function formatWhen(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function StudentDashboard({
  email,
  historyVersion,
  onStartCheckIn,
}: StudentDashboardProps) {
  const [code, setCode] = useState("");
  const { accessToken } = useAuth();
  const [pending, setPending] = useState(false);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("attendance");
    if (value) setCode(value);
  }, []);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<LessonHistoryItem[]>([]);

  useEffect(() => {
    setHistory(loadLessonHistory(email));
  }, [email, historyVersion]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) { setError("Please sign in again."); return; }
    setPending(true); setError(null);
    try {
      const lesson = await resolveAttendance(code.trim(), accessToken);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      onStartCheckIn(lesson);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to find lesson."); }
    finally { setPending(false); }
  }

  return (
    <div className="flex w-full max-w-lg flex-col gap-4 px-4 py-6 animate-fade-up sm:py-8">
      <GlassCard className="p-6 sm:p-8">
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-white/70">
          Student dashboard
        </p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-white">
          Join a class
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Scan your tutor’s QR with your phone camera to open this page, or enter the attendance passcode below. Then complete camera and location verification.
        </p>

        <form className="mt-5 space-y-3" onSubmit={onSubmit}>
          <label className="block text-sm font-medium text-white/90">
            Attendance passcode
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. ABCD 2345"
              required maxLength={16} autoComplete="off"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 uppercase tracking-wide text-white outline-none placeholder:normal-case placeholder:tracking-normal placeholder:text-white/40"
            />
          </label>
          <p className="text-xs text-white/55">You must be enrolled in the course. Ask your tutor if the code has expired.</p>
          {error && <p className="text-sm text-rose-200">{error}</p>}
          <button
            type="submit" disabled={pending}
            className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white"
          >
            {pending ? "Checking code…" : "Continue to verification"}
          </button>
        </form>
      </GlassCard>

      <GlassCard className="p-6 sm:p-7">
        <h2 className="font-display text-xl font-semibold text-white">
          Attendance submissions
        </h2>
        <p className="mt-1 text-sm text-white/70">
          Your recent submissions on this device. Approval is shown for each entry.
        </p>
        {history.length === 0 ? (
          <p className="mt-4 text-sm text-white/60">No verified lessons yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-white/10">
            {history.map((item) => (
              <li key={item.id} className="py-3">
                <p className="font-medium text-white">{item.classTitle}</p>
                <p className="text-xs text-white/70">{item.status ?? "Previously recorded"}</p>
                <p className="text-xs uppercase tracking-wide text-white/60">
                  {item.classCode}
                </p>
                <p className="mt-1 text-sm text-white/75">{formatWhen(item.verifiedAt)}</p>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>
    </div>
  );
}
