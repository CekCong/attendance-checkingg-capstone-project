"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchSessions, type BackendCourse, type BackendSession } from "@/lib/instructorApi";
import { addDays, addMonths, monthDays, CALENDAR_TIMEZONE, layoutDay, localInstant, minutesInDay, parseSessionDate, singaporeDate, timeLabel, weekStart } from "@/lib/calendar";
import { LessonScheduler } from "./LessonScheduler";

type Props = { accessToken: string | null; courses: BackendCourse[]; courseId: string; onCourseChange: (id: string) => void; onChanged: () => void; onSelectLesson: (lesson: BackendSession) => void; refreshKey: number };
const palette = [
  { background: "#fff0db", border: "#f28c18", ink: "#8b4500" },
  { background: "#e5f1ff", border: "#4389db", ink: "#1d5489" },
  { background: "#eee8ff", border: "#9873d7", ink: "#65429a" },
  { background: "#e1f4eb", border: "#3b9d74", ink: "#226f50" },
];
function colors(id: string) { return palette[Array.from(id).reduce((sum, char) => sum + char.charCodeAt(0), 0) % palette.length]; }
const headingDate = (day: string, options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-SG", { ...options, timeZone: CALENDAR_TIMEZONE }).format(new Date(`${day}T12:00:00+08:00`));

export function SessionCalendar({ accessToken, courses, courseId, onCourseChange, onChanged, onSelectLesson, refreshKey }: Props) {
  const [anchor, setAnchor] = useState(singaporeDate());
  const [view, setView] = useState<"week" | "day" | "month">("week");
  const [now, setNow] = useState(new Date());
  const [lessons, setLessons] = useState<BackendSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scheduler, setScheduler] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  const today = singaporeDate(now);
  const start = view === "month" ? monthDays(anchor)[0] : view === "week" ? weekStart(anchor) : anchor;
  const length = view === "month" ? 42 : view === "week" ? 7 : 1;
  const days = useMemo(() => Array.from({ length }, (_, index) => addDays(start, index)), [start, length]);
  function chooseLesson(lesson: BackendSession) { setSelectedId(lesson.id); onSelectLesson(lesson); }

  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 60000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 7 * 60; }, [view]);
  useEffect(() => {
    if (!accessToken) return;
    let active = true;
    let busy = false;
    setLessons([]); setSelectedId(null); setLoading(true); setError(null);
    async function load() {
      if (busy) return;
      busy = true;
      try {
        const result = await fetchSessions(accessToken!, { start: localInstant(start), end: localInstant(addDays(start, length)) });
        if (active) { setLessons(result); setError(null); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : "Unable to load calendar."); }
      finally { busy = false; if (active) setLoading(false); }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => { active = false; clearInterval(timer); };
  }, [accessToken, start, length, revision, refreshKey]);


  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white text-slate-900 shadow-lg" style={{ colorScheme: "light" }} aria-label="Lesson calendar">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 p-5 sm:px-6">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Lesson calendar · Singapore time</p>
          <h2 className="text-3xl tracking-tight"><strong>{headingDate(anchor, { month: "long" })}</strong> <span className="font-light">{headingDate(anchor, { year: "numeric" })}</span></h2>
          <p className="mt-1 text-xs text-slate-500">{view === "month" ? "Month overview" : headingDate(start, { day: "numeric", month: "short" })}{view === "week" ? ` – ${headingDate(days[6], { day: "numeric", month: "short", year: "numeric" })}` : ""}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl bg-slate-100 p-1" aria-label="Calendar view">
            {(["day", "week", "month"] as const).map((mode) => <button key={mode} type="button" aria-pressed={view === mode} onClick={() => setView(mode)} className={`rounded-lg px-3 py-1.5 text-sm capitalize ${view === mode ? "bg-white font-semibold shadow-sm" : "text-slate-500"}`}>{mode}</button>)}
          </div>
          <button type="button" aria-label={`Previous ${view}`} onClick={() => { setAnchor(view === "month" ? addMonths(anchor, -1) : addDays(anchor, -length)); setNotice(null); }} className="rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50">‹</button>
          <button type="button" onClick={() => { setAnchor(today); setNotice(null); }} className="rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">Today</button>
          <button type="button" aria-label={`Next ${view}`} onClick={() => { setAnchor(view === "month" ? addMonths(anchor, 1) : addDays(anchor, length)); setNotice(null); }} className="rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50">›</button>
          <button type="button" disabled={!courses.length} onClick={() => setScheduler(!scheduler)} aria-expanded={scheduler}
            className="rounded-xl bg-orange-600 px-4 py-2 text-sm font-semibold text-[white] hover:bg-orange-700 disabled:opacity-50">+ Add lesson</button>
        </div>
      </div>
      {scheduler && accessToken && <LessonScheduler accessToken={accessToken} courses={courses} courseId={courseId} onCourseChange={onCourseChange}
        onClose={() => setScheduler(false)} onSaved={(day, message) => { setScheduler(false); setAnchor(day); setNotice(message); setRevision((value) => value + 1); onChanged(); }} />}
      {!courses.length && <p className="border-b border-slate-200 bg-slate-50 px-6 py-3 text-sm text-slate-600">Add an existing course above to start scheduling your lessons.</p>}
      {notice && <p role="status" className="border-b border-emerald-100 bg-emerald-50 px-6 py-3 text-sm text-emerald-800">{notice}</p>}
      {error && <div role="alert" className="flex items-center justify-between bg-red-50 px-6 py-3 text-sm text-red-800">{error}<button type="button" className="ml-3 underline" onClick={() => setRevision((value) => value + 1)}>Retry</button></div>}
      <div className="flex justify-between border-b border-slate-100 px-6 py-2 text-xs text-slate-500" aria-live="polite">
        <span>{loading ? "Loading lessons…" : `${lessons.length} ${lessons.length === 1 ? "lesson" : "lessons"} ${view === "month" ? "in view" : `this ${view}`}${!lessons.length ? " · Your timetable is clear" : " · Select a lesson for details"}`}</span>
        <span>SGT · UTC+8</span>
      </div>
      {view === "month" ? (
        <div className="overflow-x-auto">
          <div className="min-w-[480px]">
            <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-center text-xs font-semibold text-slate-500">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => <div key={day} className="py-2">{day}</div>)}
            </div>
            <div className="grid grid-cols-7">
              {days.map((day) => {
                const events = layoutDay(lessons, day);
                return <div key={day} className={`min-h-[88px] border-b border-r border-slate-100 p-1 ${day.slice(0, 7) === anchor.slice(0, 7) ? "bg-white" : "bg-slate-50"}`}>
                  <button type="button" aria-label={`View lessons on ${day}`} onClick={() => { setAnchor(day); setView("day"); }}
                    className={`mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs ${day === today ? "bg-red-500 text-[white]" : "text-slate-500"}`}>{Number(day.slice(-2))}</button>
                  {events.slice(0, 2).map(({ event }) => <button key={event.id} type="button" onClick={() => chooseLesson(event)}
                    title={`${event.name} · ${timeLabel(event.scheduled_start)}`}
                    className={`mb-0.5 block w-full truncate rounded px-1 py-1 text-left text-[10px] font-medium ${selectedId === event.id ? "ring-1 ring-orange-500" : ""}`}
                    style={{ background: colors(event.course_id).background, color: colors(event.course_id).ink }}>
                    {timeLabel(event.scheduled_start)} {event.course_code}
                  </button>)}
                  {events.length > 2 && <button type="button" onClick={() => { setAnchor(day); setView("day"); }} className="text-[10px] text-slate-500">+{events.length - 2} more</button>}
                </div>;
              })}
            </div>
          </div>
        </div>
      ) : <div ref={scroll} className="max-h-[480px] overflow-auto overscroll-contain" aria-busy={loading}>
        <div style={{ minWidth: view === "week" ? 580 : 280 }}>
          <div className="sticky top-0 z-30 grid border-b border-slate-200 bg-white" style={{ gridTemplateColumns: `60px repeat(${length}, minmax(0, 1fr))` }}>
            <div className="flex items-end justify-center pb-3 text-[10px] text-slate-400">SGT</div>
            {days.map((day) => <button key={day} type="button" onClick={() => { setAnchor(day); setView("day"); }} aria-label={`Show ${headingDate(day, { weekday: "long", day: "numeric", month: "long" })}`}
              className={`flex items-center justify-center gap-2 border-l border-slate-100 py-3 text-sm ${day === today ? "text-red-600" : "text-slate-500"}`}>
              {headingDate(day, { weekday: "short" })}<span className={`flex h-8 w-8 items-center justify-center rounded-full text-xl ${day === today ? "bg-red-500 text-[white]" : "text-slate-800"}`}>{Number(day.slice(-2))}</span>
            </button>)}
          </div>
          <div className="grid" style={{ gridTemplateColumns: `60px repeat(${length}, minmax(0, 1fr))`, height: 1440 }}>
            <div className="relative bg-white text-right text-[11px] text-slate-400">
              {Array.from({ length: 24 }, (_, hour) => <div key={hour} className="absolute right-2" style={{ top: hour * 60 + 3 }}>{hour === 0 ? "12 AM" : hour === 12 ? "12 PM" : `${hour % 12} ${hour < 12 ? "AM" : "PM"}`}</div>)}
            </div>
            {days.map((day) => <div key={day} className={`relative border-l border-slate-200 ${day === today ? "bg-orange-50/20" : "bg-white"}`}
              style={{ backgroundImage: "repeating-linear-gradient(to bottom, transparent 0, transparent 29px, #f3f4f6 29px, #f3f4f6 30px, transparent 30px, transparent 59px, #e5e7eb 59px, #e5e7eb 60px)" }}>
              {layoutDay(lessons, day).map(({ event, start: minute, end, column, columns }) => {
                const color = event.status === "cancelled" || event.status === "closed" ? { background: "#f1f2f4", border: "#9ca3af", ink: "#52525b" } : colors(event.course_id);
                return <button key={event.id} type="button" onClick={() => chooseLesson(event)}
                  aria-label={`${event.course_code}, ${event.name}, ${timeLabel(event.scheduled_start)} to ${timeLabel(event.scheduled_end)}, ${event.status}`}
                  title={`${event.name}\n${timeLabel(event.scheduled_start)}–${timeLabel(event.scheduled_end)}\n${event.venue_name || ""}`}
                  className={`absolute z-10 overflow-hidden rounded-md border-l-[3px] px-1.5 py-1 text-left text-[11px] leading-tight shadow-sm transition hover:brightness-95 focus:z-20 focus:outline focus:outline-2 focus:outline-orange-500 ${selectedId === event.id ? "ring-2 ring-orange-500" : ""}`}
                  style={{ top: minute, height: Math.max(22, end - minute - 2), left: `calc(${column * 100 / columns}% + 2px)`, width: `calc(${100 / columns}% - 4px)`, background: color.background, borderColor: color.border, color: color.ink }}>
                  <span className="block font-bold">{event.course_code} · {event.name}{event.series_id ? " ↻" : ""}</span>
                  <span className="mt-0.5 block">{timeLabel(event.scheduled_start)}–{timeLabel(event.scheduled_end)}</span>
                  {event.venue_name && <span className="mt-0.5 block">⌖ {event.venue_name}</span>}
                  {event.status === "active" && <span className="mt-1 inline-block rounded bg-emerald-700 px-1 text-[white]">LIVE</span>}
                </button>;
              })}
              {day === today && <div className="pointer-events-none absolute inset-x-0 z-20 border-t-2 border-red-500" style={{ top: minutesInDay(now) }}><span className="absolute -left-1.5 -top-1.5 h-2.5 w-2.5 rounded-full bg-red-500" /></div>}
            </div>)}
          </div>
        </div>
      </div>}
      <p className="border-t border-slate-200 px-6 py-3 text-xs text-slate-500">Recurring lessons are marked ↻. Each date has its own attendance and session controls.</p>
    </section>
  );
}
