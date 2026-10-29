"use client";
import { useEffect, useState } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import {
  studentList,
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
  const [sessions, setSessions] = useState<StudentSession[]>([]);
  const [history, setHistory] = useState<Attendance[]>([]);
  const [selected, setSelected] = useState("");
  const [qrCode, setQrCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([
      studentList<StudentSession>(
        "/sessions/my-sessions?status=active",
        token,
      ),
      studentList<Attendance>("/checkins/my-checkins", token),
    ])
      .then(([items, records]) => {
        if (active) {
          setSessions(items);
          setHistory(records);
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
  const session = sessions.find((item) => item.id === selected);
  const openSessions = sessions.filter(
    (item) =>
      serverTime(item.checkin_opens_at) <= Date.now() &&
      serverTime(item.checkin_closes_at) >= Date.now(),
  );
  return (
    <div className="flex w-full flex-col gap-4">
      <GlassCard className="p-6">
        <h1 className="font-display text-3xl font-semibold text-white">
          Join a class
        </h1>
        <p className="mt-2 text-white/80">
          Choose an active session for a course you are enrolled in.
        </p>
        {loading ? (
          <p className="mt-4">Loading sessions…</p>
        ) : (
          <>
            {openSessions.length === 0 && (
              <p className="mt-4">
                No sessions are open. Ask your instructor about course
                enrollment or the check-in window.
              </p>
            )}
            <label className="mt-4 block">
              Session
              <select
                aria-label="Session"
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setQrCode("");
                }}
                className="mt-2 w-full rounded-xl bg-sky-950 p-3 text-white"
              >
                <option value="">Select a session</option>
                {openSessions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            {session?.qr_code_enabled && (
              <label className="mt-4 block">
                Session verification code
                <input
                  value={qrCode}
                  onChange={(e) => setQrCode(e.target.value)}
                  className="mt-2 w-full rounded-xl bg-sky-950 p-3 text-white"
                />
                <span className="text-sm">
                  Enter the current code provided by your instructor.
                </span>
              </label>
            )}
            <button
              disabled={!session || (session.qr_code_enabled && !qrCode.trim())}
              onClick={() => session && onStartCheckIn(session, qrCode.trim())}
              className="mt-5 w-full rounded-xl bg-white p-3 font-semibold text-sky-950 disabled:opacity-40"
            >
              Continue to verification
            </button>
          </>
        )}
        {error && (
          <p role="alert" className="mt-3 text-rose-200">
            {error}
          </p>
        )}
        <button
          onClick={() => setRevision((v) => v + 1)}
          className="mt-4 underline"
        >
          Refresh sessions and history
        </button>
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
              <time>
                {new Date(serverTime(item.checked_in_at)).toLocaleString()}
              </time>
            </li>
          ))}
        </ul>
      </GlassCard>
    </div>
  );
}
