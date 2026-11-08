"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { addExistingCourse, fetchAvailableCourses, type BackendCourse } from "@/lib/instructorApi";
import { DeleteCourseControl, type Deletion } from "./DeleteCourseControl";
import { CourseRoster } from "./CourseRoster";

type Props = {
  accessToken: string | null;
  canAddCourse: boolean;
  courses: BackendCourse[];
  selectedCourseId: string;
  onSelect: (id: string) => void;
  onAdded: (course: BackendCourse) => void;
  onDeleted: (deletion: Deletion) => void;
};

const selectClass = "mt-1 w-full rounded-2xl border border-white/25 bg-sky-950/80 px-4 py-3 text-white outline-none disabled:opacity-60";

export function CourseManager({ accessToken, canAddCourse, courses, selectedCourseId, onSelect, onAdded, onDeleted }: Props) {
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState<BackendCourse[]>([]);
  const [courseToAdd, setCourseToAdd] = useState("");
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const operation = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const selectedCourse = courses.find((course) => course.id === selectedCourseId);
  const choices = available.filter((course) => !courses.some((owned) => owned.id === course.id));

  useEffect(() => () => { operation.current += 1; }, []);
  useEffect(() => {
    if (!open || !accessToken || !canAddCourse) return;
    let active = true;
    setLoading(true);
    setError(null);
    setAvailable([]);
    void fetchAvailableCourses(accessToken).then((items) => {
      if (active) {
        setAvailable(items);
        setCourseToAdd((id) => items.some((course) => course.id === id) ? id : "");
      }
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : "Unable to load available courses.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, accessToken, canAddCourse, refresh]);

  async function addCourse(event: FormEvent) {
    event.preventDefault();
    if (busy.current || loading || !accessToken || !canAddCourse || !choices.some((course) => course.id === courseToAdd)) return;
    busy.current = true;
    const current = operation.current;
    setPending(true); setError(null); setNotice(null);
    try {
      const course = await addExistingCourse(accessToken, courseToAdd);
      if (current !== operation.current) return;
      onAdded(course);
      setCourseToAdd(""); setOpen(false);
      setNotice(`${course.code} added and selected. You can now schedule a lesson.`);
    } catch (err) {
      if (current === operation.current) setError(err instanceof Error ? err.message : "Unable to add course.");
    } finally {
      busy.current = false;
      if (current === operation.current) setPending(false);
    }
  }

  return (
    <GlassCard className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold text-white">Your courses</h2>
          <p className="mt-1 text-sm text-white/70">Select a course to schedule a lesson{canAddCourse ? ", or add one from the existing course catalog." : "."}</p>
        </div>
        {canAddCourse && <button type="button" disabled={pending || !accessToken} aria-expanded={open} aria-controls="add-course-form"
          onClick={() => { setOpen(!open); setError(null); setNotice(null); setCourseToAdd(""); }}
          className="rounded-2xl border border-white/30 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-60">
          {open ? "Cancel" : "Add existing course"}
        </button>}
      </div>
      <label className="mt-4 block text-sm text-white/90">
        Course for new sessions
        <select value={selectedCourseId} disabled={pending || !courses.length}
          onChange={(event) => { onSelect(event.target.value); setNotice(null); }} className={selectClass}>
          <option value="">{courses.length ? "Select a course" : "No courses added yet"}</option>
          {courses.map((course) => <option key={course.id} value={course.id}>{course.code} — {course.name} ({course.semester})</option>)}
        </select>
      </label>
      {selectedCourse && <CourseRoster key={`roster-${selectedCourse.id}`} courseId={selectedCourse.id} courseCode={selectedCourse.code} accessToken={accessToken} />}
      {selectedCourse && <DeleteCourseControl key={`delete-${selectedCourse.id}`} course={selectedCourse} accessToken={accessToken}
        disabled={pending} onDeleted={(deletion) => { setNotice(null); onDeleted(deletion); }} />}
      {open && canAddCourse && <form id="add-course-form" onSubmit={addCourse} className="mt-5 space-y-4 border-t border-white/15 pt-5">
        <p className="text-sm text-white/70">Choose an active course created by an administrator. Courses already assigned to another tutor are unavailable.</p>
        {loading ? <p role="status">Loading available courses…</p> : choices.length ? <label className="block text-sm text-white/90">
          Available course
          <select required disabled={pending} value={courseToAdd} onChange={(event) => setCourseToAdd(event.target.value)} className={selectClass}>
            <option value="">Choose an existing course</option>
            {choices.map((course) => <option key={course.id} value={course.id}>{course.code} — {course.name} ({course.semester})</option>)}
          </select>
        </label> : !error && <p role="status" className="text-sm text-white/80">No unassigned courses are available. Ask an administrator to create or assign a course.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={pending || loading || !choices.some((course) => course.id === courseToAdd)}
            className="rounded-2xl bg-white/90 px-5 py-3 font-semibold text-sky-950 disabled:opacity-40">
            {pending ? "Adding course…" : "Add to my courses"}
          </button>
          <button type="button" disabled={pending || loading} onClick={() => setRefresh((value) => value + 1)} className="text-sm underline disabled:opacity-40">Refresh available courses</button>
        </div>
      </form>}
      {error && <p role="alert" className="mt-3 rounded-xl bg-rose-500/20 px-3 py-2 text-sm text-rose-100">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-white/90">{notice}</p>}
    </GlassCard>
  );
}
