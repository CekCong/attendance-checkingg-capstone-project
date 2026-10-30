"use client";
import { useEffect, useState } from "react";
import { SessionQrScanner } from "@/components/check-in/SessionQrScanner";
import { GlassCard } from "@/components/check-in/GlassCard";
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
  const [sessions, setSessions] = useState<StudentSession[]>([]);
  const [history, setHistory] = useState<Attendance[]>([]);
  const [selected, setSelected] = useState("");
  const [qrCode, setQrCode] = useState("");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [passcode, setPasscode] = useState("");
  const [resolving, setResolving] = useState(false);
  useEffect(() => {
    const readCode = () => {
      const code = new URLSearchParams(window.location.hash.slice(1)).get("attendance");
      if (code) setPasscode(code.slice(0, 32));
    };
    readCode();
    window.addEventListener("hashchange", readCode);
    return () => window.removeEventListener("hashchange", readCode);
  }, []);

  async function joinByCode() {
    setResolving(true); setError("");
    try {
      const resolved = await studentRequest<{ session_id: string; qr_code: string }>("/attendance/resolve", token, {
        method: "POST", body: JSON.stringify({ code: passcode }),
      });
      const selectedSession = await studentRequest<StudentSession>(`/sessions/${resolved.session_id}`, token);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      onStartCheckIn(selectedSession, resolved.qr_code);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to join this lesson."); }
    finally { setResolving(false); }
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
          Scan your tutor's QR with your phone camera, enter a passcode, or choose an active session below.
        </p>
        <form className="mt-4 rounded-xl border border-white/25 p-3" onSubmit={(event) => { event.preventDefault(); void joinByCode(); }}>
          <label className="block text-sm text-white">Attendance passcode
            <input value={passcode} onChange={(event) => setPasscode(event.target.value)} maxLength={32} required
              autoCapitalize="characters" autoComplete="off" spellCheck={false} placeholder="e.g. ABCD 2345"
              className="mt-2 w-full rounded-xl border border-white/25 bg-sky-950/80 p-3 font-mono text-white" />
          </label>
          <button disabled={resolving || !passcode.trim()} className="mt-3 w-full rounded-xl bg-white/90 p-3 font-semibold text-sky-950 disabled:opacity-40">
            {resolving ? "Checking code…" : "Join with passcode"}
          </button>
        </form>
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
                  setScanning(false);
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
              <div>
              <label className="mt-4 block">
                Session verification code
                <input
                  aria-label="Session verification code"
                  aria-describedby="session-code-help"
                  value={qrCode}
                  onChange={(e) => setQrCode(e.target.value)}
                  className="mt-2 w-full rounded-xl bg-sky-950 p-3 text-white"
                />
                <span id="session-code-help" className="text-sm">
                  Enter the current code provided by your instructor.
                </span>
              </label>
              <p className="mt-2 text-sm">Scanning uses your camera locally. QR images are not uploaded or saved.</p>
              {scanning ? <SessionQrScanner sessionId={session.id}
                onCode={(code) => { setQrCode(code); setScanning(false); }}
                onClose={() => setScanning(false)} /> :
                <button type="button" onClick={() => setScanning(true)} className="mt-3 underline">Scan session QR code</button>}
              </div>
            )}
            <button
              disabled={scanning || !session || (session.qr_code_enabled && !qrCode.trim())}
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
