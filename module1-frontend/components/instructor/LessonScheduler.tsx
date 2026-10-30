"use client";

import { useRef, useState, type FormEvent } from "react";
import { createBackendSession, createRecurringLessons, type BackendCourse, type LessonPayload } from "@/lib/instructorApi";
import { addDays, localInstant, recurringDates, singaporeDate, WEEKDAYS } from "@/lib/calendar";

const field = "mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100";

type Props = { accessToken: string; courses: BackendCourse[]; courseId: string; onCourseChange: (id: string) => void; onSaved: (day: string, message: string) => void; onClose: () => void };
export function LessonScheduler({ accessToken, courses, courseId, onCourseChange, onSaved, onClose }: Props) {
  const [repeat, setRepeat] = useState(true);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<LessonPayload["session_type"]>("tutorial");
  const [startDate, setStartDate] = useState(singaporeDate());
  const [endDate, setEndDate] = useState(addDays(singaporeDate(), 84));
  const [weekday, setWeekday] = useState(0);
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("10:00");
  const [venue, setVenue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const lastRequest = useRef<{ signature: string; id: string } | null>(null);
  const dates = repeat ? recurringDates(startDate, endDate, weekday) : startDate ? [startDate] : [];
  const first = dates[0];
  const course = courses.find((item) => item.id === courseId);
  const past = Boolean(first && startTime && new Date(localInstant(first, startTime)) <= new Date());
  const invalidRange = !dates.length || (repeat && (endDate < startDate || endDate > addDays(startDate, 366)));
  const validTime = startTime && endTime && endTime > startTime;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!course || !name.trim() || !validTime || invalidRange || past) {
      setError("Choose a course and valid future lesson dates and times."); return;
    }
    setPending(true);
    try {
      const base = { course_id: courseId, name: name.trim(), session_type: kind, venue_name: venue.trim() || undefined };
      let count = 1;
      if (repeat) {
        const schedule = { ...base, start_date: startDate, end_date: endDate, weekday, start_time: startTime, end_time: endTime, timezone: "Asia/Singapore" as const };
        const signature = JSON.stringify(schedule);
        if (lastRequest.current?.signature !== signature) lastRequest.current = { signature, id: crypto.randomUUID() };
        const result = await createRecurringLessons(accessToken, { ...schedule, request_id: lastRequest.current.id });
        count = result.count;
      } else {
        await createBackendSession(accessToken, { ...base, scheduled_start: localInstant(startDate, startTime), scheduled_end: localInstant(startDate, endTime) });
      }
      onSaved(first, `${count} ${count === 1 ? "lesson" : "weekly lessons"} added to ${course.code}.`);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save lessons. Please try again."); }
    finally { setPending(false); }
  }

  return (
    <section className="border-b border-slate-200 bg-slate-50 p-5 sm:p-6" aria-labelledby="schedule-title">
      <div className="mb-4 flex items-center justify-between">
        <div><h3 id="schedule-title" className="text-lg font-semibold text-slate-900">Schedule a lesson</h3><p className="text-sm text-slate-500">All dates and times are in Singapore (SGT).</p></div>
        <button type="button" onClick={onClose} disabled={pending} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-200">Cancel</button>
      </div>
      <form onSubmit={submit}>
        <fieldset disabled={pending} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2">
          <label className="text-sm font-medium text-slate-700">Course
            <select required value={courseId} onChange={(event) => onCourseChange(event.target.value)} className={field}>
              <option value="">Choose a course</option>{courses.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.semester}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700 lg:col-span-2">Lesson title
            <input required maxLength={255} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Machine Learning tutorial" className={field} />
          </label>
          <label className="text-sm font-medium text-slate-700">Lesson type
            <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)} className={field}>
              <option value="tutorial">Tutorial</option><option value="lecture">Lecture</option><option value="lab">Lab</option><option value="exam">Exam</option>
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">Repeats
            <select value={repeat ? "weekly" : "once"} onChange={(event) => setRepeat(event.target.value === "weekly")} className={field}>
              <option value="weekly">Every week</option><option value="once">Does not repeat</option>
            </select>
          </label>
          {repeat && <label className="text-sm font-medium text-slate-700">Day of week
            <select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))} className={field}>
              {WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
            </select>
          </label>}
          <label className="text-sm font-medium text-slate-700">{repeat ? "Starts on or after" : "Lesson date"}
            <input type="date" required min={singaporeDate()} value={startDate} onChange={(event) => setStartDate(event.target.value)} className={field} />
          </label>
          {repeat && <label className="text-sm font-medium text-slate-700">Ends on or before
            <input type="date" required min={startDate} max={startDate ? addDays(startDate, 366) : undefined} value={endDate} onChange={(event) => setEndDate(event.target.value)} className={field} />
          </label>}
          <label className="text-sm font-medium text-slate-700">Start time
            <input type="time" required value={startTime} onChange={(event) => setStartTime(event.target.value)} className={field} />
          </label>
          <label className="text-sm font-medium text-slate-700">End time
            <input type="time" required value={endTime} onChange={(event) => setEndTime(event.target.value)} className={field} />
          </label>
          <label className="text-sm font-medium text-slate-700 sm:col-span-2">Location <span className="font-normal text-slate-400">(optional)</span>
            <input value={venue} maxLength={255} onChange={(event) => setVenue(event.target.value)} placeholder="e.g. LT2A or Tutorial Room 4" className={field} />
          </label>
          <div className="rounded-xl border border-orange-200 bg-orange-50 p-3 text-sm text-orange-900 sm:col-span-2 lg:col-span-2" role="status">
            {invalidRange ? "Choose a date range containing at least one lesson, up to one year."
              : !validTime ? "Choose an end time later than the start time. Lessons must finish on the same day."
                : past ? "The first lesson would be in the past. Choose a later start date or time."
                  : `${dates.length} ${dates.length === 1 ? "lesson" : "lessons"}${repeat ? ` · Every ${WEEKDAYS[weekday]}` : ""} · ${startTime}–${endTime} SGT · ${first}${repeat ? ` to ${dates[dates.length - 1]}` : ""}`}
          </div>
          {error && <p role="alert" className="text-sm text-red-700 sm:col-span-2 lg:col-span-2">{error}</p>}
          <div className="flex justify-end sm:col-span-2 lg:col-span-2">
            <button type="submit" disabled={pending || !courseId || !name.trim() || !validTime || invalidRange || past}
              className="rounded-xl bg-orange-600 px-5 py-2.5 font-semibold text-[white] hover:bg-orange-700 disabled:opacity-50">
              {pending ? "Saving lessons…" : repeat ? `Schedule ${dates.length} lessons` : "Add lesson"}
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
