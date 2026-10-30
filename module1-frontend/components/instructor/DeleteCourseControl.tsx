"use client";

import { useState } from "react";
import { deleteCourseOrLesson, type BackendSession } from "@/lib/instructorApi";
import { CALENDAR_TIMEZONE, parseSessionDate, timeLabel } from "@/lib/calendar";

export type Deletion = { courseId: string; lessonId?: string };
type Props = {
  accessToken: string | null;
  course: { id: string; code: string; name: string };
  lesson?: BackendSession;
  disabled?: boolean;
  onDeleted: (deletion: Deletion) => void;
};

export function DeleteCourseControl({ accessToken, course, lesson, disabled, onDeleted }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [scope, setScope] = useState<"lesson" | "course">(lesson ? "lesson" : "course");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const date = lesson ? new Intl.DateTimeFormat("en-SG", {
    timeZone: CALENDAR_TIMEZONE, weekday: "short", day: "numeric", month: "short", year: "numeric",
  }).format(parseSessionDate(lesson.scheduled_start)) : "";

  async function remove() {
    if (!accessToken || pending) return;
    setPending(true); setError(null);
    try {
      await deleteCourseOrLesson(accessToken, scope, scope === "lesson" && lesson ? lesson.id : course.id);
      onDeleted({ courseId: course.id, ...(scope === "lesson" && lesson ? { lessonId: lesson.id } : {}) });
      setExpanded(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to delete."); }
    finally { setPending(false); }
  }

  return <div className="mt-4 border-t border-white/15 pt-3">
    {!expanded ? <button type="button" disabled={disabled || !accessToken} onClick={() => setExpanded(true)} aria-expanded={false}
      className="danger-trigger flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold disabled:opacity-50">
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg>
      {lesson ? "Delete lesson or course…" : "Delete course…"}
    </button> : <div className="danger-surface rounded-xl p-4">
      <fieldset disabled={pending || disabled} className="space-y-3 text-sm">
        <legend className="mb-3 font-semibold">Delete from {course.code} — {course.name}</legend>
        {lesson && <label className="flex cursor-pointer items-start gap-2">
          <input type="radio" name={`delete-scope-${lesson.id}`} checked={scope === "lesson"} onChange={() => setScope("lesson")} className="mt-1" />
          <span><strong className="block">Delete this lesson only</strong>{lesson.name}<br />{date} · {timeLabel(lesson.scheduled_start)}–{timeLabel(lesson.scheduled_end)} SGT</span>
        </label>}
        <label className="flex cursor-pointer items-start gap-2">
          <input type="radio" name={`delete-scope-${lesson?.id ?? course.id}`} checked={scope === "course"} onChange={() => setScope("course")} className="mt-1" />
          <span><strong className="block">Delete all</strong>The entire course and all its lessons, on every date.</span>
        </label>
        <p className="text-xs leading-relaxed">{scope === "lesson"
          ? "This permanently deletes this lesson and its attendance records. Other dates and lessons stay in the calendar."
          : "This permanently deletes this course, all its lessons, enrollments, and attendance records."} This cannot be undone.</p>
        {!lesson && <p className="text-xs">To delete one specific lesson, select it in the calendar instead.</p>}
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void remove()} className="danger-confirm rounded-lg px-3 py-2 font-semibold disabled:opacity-50">
            {pending ? "Deleting…" : scope === "lesson" ? "Confirm delete lesson" : "Confirm delete all"}
          </button>
          <button type="button" onClick={() => { setExpanded(false); setError(null); }} className="rounded-lg border border-current px-3 py-2">Cancel</button>
        </div>
      </fieldset>
      {error && <p role="alert" className="mt-3 text-sm">{error}</p>}
    </div>}
  </div>;
}
