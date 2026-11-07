"use client";

import { useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { createBackendCourse, type BackendCourse } from "@/lib/instructorApi";
import { semesterOptions } from "@/lib/calendar";
import { DeleteCourseControl, type Deletion } from "./DeleteCourseControl";
import { CourseRoster } from "./CourseRoster";

type Props = {
  accessToken: string | null;
  courses: BackendCourse[];
  selectedCourseId: string;
  onSelect: (id: string) => void;
  onCreated: (course: BackendCourse) => void;
  onDeleted: (deletion: Deletion) => void;
};

const inputClass = "mt-1 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none placeholder:text-white/40 focus:border-white/60";

export function CourseManager({ accessToken, courses, selectedCourseId, onSelect, onCreated, onDeleted }: Props) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [semester, setSemester] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const selectedCourse = courses.find((course) => course.id === selectedCourseId);

  async function createCourse(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!accessToken) {
      setError("Sign in to create a course.");
      return;
    }
    if (!code.trim() || !name.trim() || !semester.trim()) {
      setError("Enter a course code, name, and semester.");
      return;
    }
    setPending(true);
    try {
      const course = await createBackendCourse(accessToken, {
        code: code.trim(), name: name.trim(), semester: semester.trim(),
      });
      onCreated(course);
      setCode("");
      setName("");
      setSemester("");
      setOpen(false);
      setNotice(`${course.code} created and selected. You can now schedule a session below.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create course.");
    } finally {
      setPending(false);
    }
  }

  return (
    <GlassCard className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold text-white">Your courses</h2>
          <p className="mt-1 text-sm text-white/70">Select a course to schedule a session, or create a new one.</p>
        </div>
        <button type="button" disabled={pending} aria-expanded={open} aria-controls="new-course-form"
          onClick={() => { setOpen(!open); setError(null); setNotice(null); }}
          className="rounded-2xl border border-white/30 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-60">
          {open ? "Cancel" : "New course"}
        </button>
      </div>
      <label className="mt-4 block text-sm text-white/90">
        Course for new sessions
        <select value={selectedCourseId} disabled={pending || !courses.length}
          onChange={(event) => { onSelect(event.target.value); setNotice(null); }}
          className="mt-1 w-full rounded-2xl border border-white/25 bg-sky-950/80 px-4 py-3 text-white outline-none disabled:opacity-60">
          <option value="">{courses.length ? "Select a course" : "No courses yet — create your first course"}</option>
          {courses.map((course) => (
            <option key={course.id} value={course.id}>{course.code} — {course.name} ({course.semester})</option>
          ))}
        </select>
      </label>
      {selectedCourse && <CourseRoster key={`roster-${selectedCourse.id}`} courseId={selectedCourse.id} courseCode={selectedCourse.code} accessToken={accessToken} />}
      {selectedCourse && <DeleteCourseControl key={`delete-${selectedCourse.id}`} course={selectedCourse} accessToken={accessToken}
        disabled={pending} onDeleted={(deletion) => { setNotice(null); onDeleted(deletion); }} />}
      {open && (
        <form id="new-course-form" onSubmit={createCourse} className="mt-5 border-t border-white/15 pt-5">
          <fieldset disabled={pending} className="grid gap-4 sm:grid-cols-2">
            <legend className="sr-only">New course details</legend>
            <label className="text-sm text-white/90">Course code
              <input required maxLength={20} value={code} onChange={(event) => setCode(event.target.value)}
                placeholder="e.g. SC3099" className={inputClass} />
            </label>
            <label className="text-sm text-white/90">Semester
              <select required value={semester} onChange={(event) => setSemester(event.target.value)}
                className={inputClass.replace("bg-white/15", "bg-sky-950/80")}>
                <option value="">Choose a semester</option>
                {semesterOptions().map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="text-sm text-white/90 sm:col-span-2">Course name
              <input required maxLength={255} value={name} onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Capstone Project" className={inputClass} />
            </label>
            <button type="submit" disabled={pending}
              className="rounded-2xl bg-white/90 px-5 py-3 font-semibold text-sky-950 disabled:opacity-60 sm:col-span-2">
              {pending ? "Creating course…" : "Create course"}
            </button>
          </fieldset>
        </form>
      )}
      {error && <p role="alert" className="mt-3 rounded-xl bg-rose-500/20 px-3 py-2 text-sm text-rose-100">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-white/90">{notice}</p>}
    </GlassCard>
  );
}
