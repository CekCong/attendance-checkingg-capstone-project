"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { KNOWN_CLASSES, lookupClass } from "@/lib/classes";
import { loadLessonHistory } from "@/lib/attendanceHistory";
import type { LessonHistoryItem } from "@/lib/types";

type StudentDashboardProps = {
  email: string;
  historyVersion: number;
  onStartCheckIn: (classCode: string, classTitle: string) => void;
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
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<LessonHistoryItem[]>([]);

  useEffect(() => {
    setHistory(loadLessonHistory(email));
  }, [email, historyVersion]);

  const hint = useMemo(
    () => KNOWN_CLASSES.map((item) => item.code).join(", "),
    [],
  );

  function startWithCode(raw: string) {
    const found = lookupClass(raw);
    if (!found) {
      setError("Enter a class code or scan a session QR.");
      return;
    }
    setError(null);
    onStartCheckIn(found.code, found.title);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    startWithCode(code);
  }

  function simulateScan() {
    setScanning(true);
    setError(null);
    window.setTimeout(() => {
      const sample = KNOWN_CLASSES[0];
      setCode(sample.code);
      setScanning(false);
      onStartCheckIn(sample.code, sample.title);
    }, 900);
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
          Scan the session QR or enter the class code, then complete a short
          verification. Face and location checks are stubbed for now.
        </p>

        <div className="relative mt-5 overflow-hidden rounded-2xl border border-white/20 bg-sky-950/40">
          <div className="flex aspect-[4/3] flex-col items-center justify-center gap-3 p-6">
            <div className="h-28 w-28 rounded-xl border-2 border-dashed border-white/50" />
            <p className="text-sm text-white/75">
              {scanning ? "Looking for a QR code…" : "QR scanner (stub)"}
            </p>
            <button
              type="button"
              disabled={scanning}
              onClick={simulateScan}
              className="rounded-2xl bg-white/90 px-5 py-2.5 text-sm font-semibold text-sky-950 disabled:opacity-60"
            >
              {scanning ? "Scanning…" : "Scan class QR"}
            </button>
          </div>
        </div>

        <form className="mt-5 space-y-3" onSubmit={onSubmit}>
          <label className="block text-sm font-medium text-white/90">
            Or enter class code
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. CS101-L4"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 uppercase tracking-wide text-white outline-none placeholder:normal-case placeholder:tracking-normal placeholder:text-white/40"
            />
          </label>
          <p className="text-xs text-white/55">Demo codes: {hint}</p>
          {error && <p className="text-sm text-rose-200">{error}</p>}
          <button
            type="submit"
            className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white"
          >
            Continue to verification
          </button>
        </form>
      </GlassCard>

      <GlassCard className="p-6 sm:p-7">
        <h2 className="font-display text-xl font-semibold text-white">
          Verified lessons
        </h2>
        <p className="mt-1 text-sm text-white/70">
          Previous check-ins for this session.
        </p>
        {history.length === 0 ? (
          <p className="mt-4 text-sm text-white/60">No verified lessons yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-white/10">
            {history.map((item) => (
              <li key={item.id} className="py-3">
                <p className="font-medium text-white">{item.classTitle}</p>
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
