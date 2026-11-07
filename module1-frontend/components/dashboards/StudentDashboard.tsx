"use client";
import { useEffect, useRef, useState } from "react";
import { SessionQrScanner } from "@/components/check-in/SessionQrScanner";
import { GlassCard } from "@/components/check-in/GlassCard";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  studentList,
  studentRequest,
  serverTime,
  type StudentSession,
  type Attendance,
} from "@/lib/studentApi";

export function StudentDashboard({
  token,
  onStartCheckIn,
}: {
  token: string;
  onStartCheckIn: (session: StudentSession, qrCode: string) => void;
}) {
  const { user } = useAuth();
  const [courses, setCourses] = useState<{ id: string; course_code: string; course_name: string; semester: string; is_active: boolean }[]>([]);
  const [sessions, setSessions] = useState<StudentSession[]>([]);
  const [history, setHistory] = useState<Attendance[]>([]);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [passcode, setPasscode] = useState("");
  const [resolving, setResolving] = useState(false);
  const joining = useRef(false);
  const joinPanel = useRef<HTMLDivElement>(null);
  const [retryNotice, setRetryNotice] = useState("");
  useEffect(() => {
    const readCode = () => {
      const code = new URLSearchParams(window.location.hash.slice(1)).get("attendance");
      if (code) setPasscode(code.slice(0, 32));
    };
    readCode();
    window.addEventListener("hashchange", readCode);
    return () => window.removeEventListener("hashchange", readCode);
  }, []);

  async function joinByCode(code = passcode) {
    if (joining.current || !code.trim()) return;
    joining.current = true;
    setResolving(true); setError("");
    try {
      const resolved = await studentRequest<{ session_id: string; qr_code: string }>("/attendance/resolve", token, {
        method: "POST", body: JSON.stringify({ code }),
      });
      const selectedSession = await studentRequest<StudentSession>(`/sessions/${resolved.session_id}`, token);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      onStartCheckIn(selectedSession, resolved.qr_code);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to join this lesson."); }
    finally { joining.current = false; setResolving(false); }
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([
      studentList<StudentSession>(
        "/sessions/my-sessions?status=active",
        token,
      ),
      studentList<Attendance>("/checkins/my-checkins", token),
      studentRequest<{ id: string; course_code: string; course_name: string; semester: string; is_active: boolean }[]>("/enrollments/my-enrollments", token),
    ])
      .then(([items, records, enrollments]) => {
        if (active) {
          setSessions(items);
          setHistory(records);
          setCourses(enrollments.filter((item) => item.is_active));
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, revision]);
  const openSessions = sessions.filter(
    (item) =>
      serverTime(item.checkin_opens_at) <= Date.now() &&
      serverTime(item.checkin_closes_at) >= Date.now(),
  );
  return (
    <div className="grid w-full items-start gap-5 md:grid-cols-2">
      <div ref={joinPanel} className="min-w-0">
      <GlassCard className="p-6">
        <h1 className="font-display text-3xl font-semibold text-white">
          Join a class
        </h1>
        <p className="mt-2 text-white/80">
          Enter your tutor's attendance passcode or scan their QR code. We'll find the lesson for you.
        </p>
        {retryNotice && <p role="status" className="mt-3 text-sm">{retryNotice}</p>}
        <form className="mt-4 rounded-xl border border-white/25 p-3" onSubmit={(event) => { event.preventDefault(); void joinByCode(); }}>
          <label className="block text-sm text-white">Attendance passcode
            <input value={passcode} onChange={(event) => setPasscode(event.target.value)} maxLength={32} required disabled={scanning || resolving}
              autoCapitalize="characters" autoComplete="off" spellCheck={false} placeholder="e.g. ABCD 2345"
              className="mt-2 w-full rounded-xl border border-white/25 bg-sky-950/80 p-3 font-mono text-white" />
          </label>
          <button disabled={scanning || resolving || !passcode.trim()} className="mt-3 w-full rounded-xl bg-white/90 p-3 font-semibold text-sky-950 disabled:opacity-40">
            {resolving ? "Checking code…" : "Join with passcode"}
          </button>
        </form>
        {scanning ? <SessionQrScanner
          onCode={(code) => { setPasscode(code); setScanning(false); void joinByCode(code); }}
          onClose={() => setScanning(false)} /> :
          <button type="button" disabled={resolving} onClick={() => { setError(""); setScanning(true); }}
            className="mt-4 w-full rounded-xl border border-white/30 p-3 font-semibold disabled:opacity-40">
            Scan QR code
          </button>}
        <p className="mt-2 text-sm text-white/70">Scanning uses your camera locally. QR images are not uploaded or saved.</p>
        {error && (
          <p role="alert" className="mt-3 text-rose-200">
            {error}
          </p>
        )}
        <button
          onClick={() => setRevision((v) => v + 1)}
          className="mt-4 underline"
        >
          Refresh courses and attendance
        </button>
      </GlassCard>
      </div>
      <aside className="min-w-0 space-y-5 break-words" aria-label="Courses and attendance history">
      <GlassCard className="p-5 sm:p-6">
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white [&::-webkit-details-marker]:hidden">
            <h2 className="text-xl font-semibold text-white">My courses</h2>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              className="h-5 w-5 shrink-0 text-white/80 transition-transform group-open:rotate-180">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </summary>
          {user?.matriculation_number ? <p className="mt-3 text-sm text-white/75">Matriculation number: {user.matriculation_number}</p>
            : <p className="mt-3 text-sm text-white/80"><Link href="/profile" className="font-semibold underline">Link your matriculation number in Profile</Link> to join courses from your tutor's CSV roster.</p>}
          <ul className="mt-3 space-y-2 text-sm text-white">
            {courses.map((course) => <li key={course.id} className="rounded-xl border border-white/20 p-3"><strong>{course.course_code}</strong> · {course.course_name}<span className="mt-1 block text-xs text-white/70">{course.semester}</span></li>)}
          </ul>
          {loading && <p className="mt-3 text-sm text-white/70">Loading courses…</p>}
          {!courses.length && !loading && <p className="mt-2 text-sm text-white/70">No enrolled courses yet. Ask your tutor to upload your matriculation number, then select Refresh courses and attendance.</p>}
        </details>
      </GlassCard>
      <GlassCard className="p-6">
        <h2 className="text-xl font-semibold">Attendance history</h2>
        <p className="text-sm">Your attendance records.</p>
        {!history.length && !loading && !error && (
          <p className="mt-4">No attendance records yet.</p>
        )}
        <ul>
          {history.map((item) => (
            <li key={item.id} className="border-b border-white/20 py-3">
              <p>
                {item.session_name} · {item.course_code}
              </p>
              <p className="capitalize">{item.status}</p>
              {item.biometric_demo_mode && <p className="mt-1 text-xs">Demo record · Face and liveness checks bypassed</p>}
              {item.status === "rejected" && <div className="mt-2">
                <p className="text-sm font-semibold">Why it was rejected</p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                  {(item.rejection_reasons?.length ? item.rejection_reasons : ["A detailed reason is unavailable. Contact your instructor for help."])
                    .map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
                {openSessions.some((lesson) => lesson.id === item.session_id) ? (
                  <button type="button" className="my-3 rounded-xl bg-white px-4 py-2 font-semibold text-sky-950" onClick={() => {
                    const lesson = openSessions.find((candidate) => candidate.id === item.session_id)!;
                    if (!lesson.qr_code_enabled) { onStartCheckIn(lesson, ""); return; }
                    setPasscode("");
                    setScanning(false);
                    setRetryNotice(`Retry ${lesson.name}: enter your tutor's current attendance passcode or scan their QR code.`);
                    joinPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}>Retry attendance</button>
                ) : <p className="my-2 text-sm">Attendance is not currently open. Ask your instructor to reopen it before retrying.</p>}
              </div>}
              <time>
                {new Date(serverTime(item.checked_in_at)).toLocaleString()}
              </time>
            </li>
          ))}
        </ul>
      </GlassCard>
      </aside>
    </div>
  );
}
