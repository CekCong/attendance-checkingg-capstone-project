"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { CALENDAR_TIMEZONE, parseSessionDate, timeLabel } from "@/lib/calendar";
import { updateBackendSessionStatus, type BackendSession } from "@/lib/instructorApi";
import { DeleteCourseControl, type Deletion } from "./DeleteCourseControl";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Invitation = { open: boolean; session_id: string; demo_mode?: boolean; biometric_demo_mode?: boolean; reason?: "upcoming" | "ended" | "closed" | "cancelled" | "expired" | "not_open"; passcode?: string; expires_at?: string; join_url?: string; qr_svg?: string };
type Props = { lesson: BackendSession | null; accessToken: string | null; onChanged: (lesson: BackendSession) => void; onDeleted: (deletion: Deletion) => void };

export function AttendancePanel({ lesson, accessToken, onChanged, onDeleted }: Props) {
  const [website, setWebsite] = useState("");
  const [draft, setDraft] = useState("");
  const [invite, setInvite] = useState<Invitation | null>(null);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mode, setMode] = useState<"qr" | "code">("qr");
  useEffect(() => {
    const url = new URL(window.location.origin); url.port = "3000";
    const initial = localStorage.getItem("saiv_student_website") || url.origin;
    setWebsite(initial); setDraft(initial);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    setInvite(null); setError(null); setCopied(false);
    if (!lesson || !accessToken || !website) { setLoading(false); return; }
    setLoading(true);
    let active = true;
    let fetching = false;
    const id = lesson.id;
    async function load() {
      if (fetching) return;
      fetching = true;
      try {
        const response = await fetch(`${API}/api/v1/sessions/${id}/attendance-code?student_url=${encodeURIComponent(website)}`, {
          headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load attendance code.");
        if (active) { setInvite(data); setError(null); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : "Unable to connect."); }
      finally { fetching = false; if (active) setLoading(false); }
    }
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => { active = false; clearInterval(timer); };
  }, [lesson?.id, lesson?.status, accessToken, website, revision]);

  const remaining = invite?.expires_at ? Math.max(0, Math.ceil((parseSessionDate(invite.expires_at).getTime() - now) / 1000)) : 0;
  const open = Boolean(invite?.open && invite.session_id === lesson?.id && remaining > 0);
  const demoMode = Boolean(invite?.session_id === lesson?.id && invite?.demo_mode);
  const canOpen = Boolean(lesson && (demoMode || (["scheduled", "active"].includes(lesson.status)
    && now >= parseSessionDate(lesson.scheduled_start).getTime() - 15 * 60000 && now < parseSessionDate(lesson.scheduled_end).getTime())));
  const expired = invite?.reason === "expired" || Boolean(invite?.expires_at && remaining === 0);
  const fullDate = (value: Date) => new Intl.DateTimeFormat("en-SG", {
    timeZone: CALENDAR_TIMEZONE, day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
  }).format(value);
  const opensAt = lesson ? new Date(parseSessionDate(lesson.scheduled_start).getTime() - 15 * 60000) : null;
  const ended = Boolean(lesson && now >= parseSessionDate(lesson.scheduled_end).getTime());
  let emptyTitle = "Select a lesson first";
  let emptyDetail = "Click a lesson in the calendar, then generate its QR code and passcode here.";
  if (lesson) {
    if (loading) { emptyTitle = "Checking attendance…"; emptyDetail = "Loading the current QR code and passcode."; }
    else if (error) { emptyTitle = "Unable to show attendance code"; emptyDetail = "Check the message below and retry."; }
    else if (!demoMode && (lesson.status === "closed" || lesson.status === "cancelled")) {
      emptyTitle = `Lesson ${lesson.status}`; emptyDetail = "Attendance is no longer available for this lesson. Select another lesson in the calendar.";
    } else if (!demoMode && ended) {
      emptyTitle = "This lesson has ended"; emptyDetail = "Select an upcoming or current lesson to take attendance.";
    } else if (!canOpen && opensAt) {
      emptyTitle = "Attendance is not open yet"; emptyDetail = `You can generate a code from ${fullDate(opensAt)} SGT, 15 minutes before this lesson starts.`;
    } else if (expired) {
      emptyTitle = "Your attendance code has expired"; emptyDetail = "Codes last 15 minutes. Generate a new code below so students can check in.";
    } else {
      emptyTitle = "Ready to take attendance"; emptyDetail = demoMode
        ? "Generate a real QR code and passcode now, regardless of the lesson date or time. This opens a 15-minute demo check-in window."
        : "Generate a real QR code and passcode below. This opens a 15-minute check-in window for this lesson.";
    }
  }

  async function issue() {
    if (!lesson || !accessToken) return;
    setBusy(true); setError(null); setCopied(false);
    try {
      const response = await fetch(`${API}/api/v1/sessions/${lesson.id}/attendance-code`, {
        method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ student_url: website }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to open attendance.");
      setInvite(data); onChanged({ ...lesson, status: "active" });
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to open attendance."); }
    finally { setBusy(false); }
  }
  async function close() {
    if (!lesson || !accessToken) return;
    setBusy(true); setError(null);
    try { await updateBackendSessionStatus(accessToken, lesson.id, "closed"); setInvite(null); onChanged({ ...lesson, status: "closed" }); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to close lesson."); }
    finally { setBusy(false); }
  }
  function applyWebsite() {
    try {
      const url = new URL(draft);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) throw new Error();
      const value = `${url.origin}${url.pathname.replace(/\/$/, "")}`;
      localStorage.setItem("saiv_student_website", value); setWebsite(value); setDraft(value); setError(null);
    } catch { setError("Enter a valid HTTP or HTTPS student website URL."); }
  }

  return <GlassCard className="p-5">
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">Take attendance</p>
    <h2 className="mt-1 font-display text-xl font-semibold text-white">{lesson ? lesson.course_code : "Choose a lesson"}</h2>
    {lesson ? <><p className="mt-1 text-sm text-white/80">{lesson.name}</p><p className="mt-1 text-xs text-white/60">{fullDate(parseSessionDate(lesson.scheduled_start))}–{timeLabel(lesson.scheduled_end)} SGT · {lesson.venue_name || "No location"} · {lesson.status}</p></>
      : <p className="mt-3 text-sm text-white/70">Select a lesson in the calendar to show its QR code or passcode here.</p>}
    {demoMode && <p className="mt-3 rounded-xl border border-white/25 bg-white/10 px-3 py-2 text-sm font-medium text-white">Demo mode · Attendance can be opened at any time, including for past or closed lessons.</p>}
    {invite?.biometric_demo_mode && <p className="mt-3 rounded-xl border border-amber-300/50 bg-amber-300/10 px-3 py-2 text-sm">Biometric demo mode · Face and liveness checks automatically pass. Other attendance checks still apply.</p>}
    <div className="mt-4 flex rounded-xl bg-white/10 p-1">
      {(["qr", "code"] as const).map((item) => <button key={item} type="button" aria-pressed={mode === item} onClick={() => setMode(item)} className={`flex-1 rounded-lg px-3 py-2 text-sm ${mode === item ? "bg-white/90 font-semibold text-sky-950" : "text-white/70"}`}>{item === "qr" ? "QR code" : "Passcode"}</button>)}
    </div>
    {open && invite ? <div className="mt-4 text-center">
      {mode === "qr" && invite.qr_svg && <div className="mx-auto w-fit rounded-2xl bg-white p-2"><img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(invite.qr_svg)}`} alt="Scan to join this lesson" width={208} height={208} /></div>}
      <p className="mt-3 text-xs text-white/65">{mode === "qr" ? "Scan with your phone camera, or enter" : "Enter this code in the student portal"}</p>
      <p className="mt-2 select-all font-mono text-3xl font-bold tracking-[0.15em] text-white">{invite.passcode?.slice(0, 4)} {invite.passcode?.slice(4)}</p>
      <p role="timer" className="mt-2 text-xs text-white/60">Expires in {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}</p>
      <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(invite.passcode!); setCopied(true); } catch { setError("Select the passcode above to copy it manually."); } }} className="mt-2 text-sm text-white underline">{copied ? "Copied" : "Copy passcode"}</button>
    </div> : <div role="status" className="mt-4 flex min-h-[160px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/25 px-5 py-6 text-center">
      <p className="text-base font-semibold text-white">{emptyTitle}</p>
      <p className="text-sm text-white/80">{emptyDetail}</p>
    </div>}
    {lesson && <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" disabled={busy || loading || !canOpen || !website} onClick={() => void issue()} className="flex-1 rounded-xl bg-white/90 px-3 py-3 text-sm font-semibold text-sky-950 disabled:opacity-40">{busy ? "Updating…" : open ? "Renew QR & passcode" : expired ? "Generate new QR & passcode" : "Generate QR & passcode"}</button>
      {lesson.status === "active" && <button type="button" disabled={busy} onClick={() => void close()} className="rounded-xl border border-white/30 px-3 py-2.5 text-sm text-white disabled:opacity-40">Close session</button>}
    </div>}
    {open && <p className="mt-2 text-xs text-white/55">Renewing invalidates the previous code. Students still complete verification.</p>}
    <details className="mt-4 border-t border-white/15 pt-3">
      <summary className="cursor-pointer text-xs font-medium text-white/80">Student website URL</summary>
      <label className="mt-3 block text-xs text-white/70">Address opened by the QR
        <input type="url" value={draft} onChange={(event) => setDraft(event.target.value)} className="mt-1 w-full rounded-xl border border-white/25 bg-white/10 px-3 py-2 text-sm text-white" />
      </label>
      <button type="button" onClick={applyWebsite} className="mt-2 rounded-lg border border-white/25 px-3 py-1.5 text-xs text-white">Apply URL</button>
      <p className="mt-2 text-xs text-white/60">Use a shared HTTPS student URL for phones. Localhost only works on this computer; camera and location require HTTPS on other devices.</p>
    </details>
    {error && <div role="alert" className="danger-error mt-3 rounded-xl p-3 text-sm">{error}<button type="button" onClick={() => setRevision((value) => value + 1)} className="ml-2 font-semibold underline">Retry</button></div>}
    {lesson && <DeleteCourseControl key={lesson.id} accessToken={accessToken} lesson={lesson} disabled={busy}
      course={{ id: lesson.course_id, code: lesson.course_code, name: lesson.course_name }} onDeleted={onDeleted} />}
  </GlassCard>;
}
