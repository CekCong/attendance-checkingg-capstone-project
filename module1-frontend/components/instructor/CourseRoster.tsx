"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Row = { matriculation_number: string; name: string | null; status: "pending" | "enroll" | "already_enrolled" | "blocked" };
type Preview = { total: number; duplicates: number; enrolled: number; already_enrolled: number; pending: number; items: Row[] };
const labels = { pending: "Pending signup / number link", enroll: "Ready to enroll", already_enrolled: "Enrolled", blocked: "Account unavailable" };

export function CourseRoster({ courseId, courseCode, accessToken }: { courseId: string; courseCode: string; accessToken: string | null }) {
  const [csv, setCsv] = useState("");
  const [filename, setFilename] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [roster, setRoster] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const selection = useRef(0);
  const [loading, setLoading] = useState(false);

  async function request(path: string, body?: string) {
    const response = await fetch(`${API}/api/v1/enrollments/course/${courseId}/${path}`, {
      method: body === undefined ? "GET" : "POST", body, cache: "no-store", signal: AbortSignal.timeout(30_000),
      headers: { Authorization: `Bearer ${accessToken}`, ...(body === undefined ? {} : { "Content-Type": "text/csv; charset=utf-8" }) },
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message
        ? `${detail.message} ${(detail.rows ?? []).map((row: { row: number; message: string }) => `Row ${row.row}: ${row.message}`).join(" ")}`
        : "Unable to load or import this roster.");
    }
    return data;
  }

  useEffect(() => {
    if (!accessToken) return;
    let active = true;
    setLoading(true);
    void request("roster").then((data) => { if (active) setRoster(data.items); })
      .catch((err) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [courseId, accessToken, revision]);

  async function selectFile(file?: File) {
    const current = ++selection.current;
    setPreview(null); setError(null); setNotice(null); setCsv(""); setFilename(file?.name ?? "");
    if (!file) return;
    if (file.size > 1_000_000) { setError("Choose a CSV smaller than 1 MB."); return; }
    setBusy(true);
    try {
      const content = await file.text();
      const data = await request("csv?preview=true", content);
      if (current === selection.current) { setCsv(content); setPreview(data); }
    } catch (err) { if (current === selection.current) setError(err instanceof Error ? err.message : "Unable to preview CSV."); }
    finally { if (current === selection.current) setBusy(false); }
  }

  async function importCsv() {
    setBusy(true); setError(null);
    try {
      const result: Preview = await request("csv?preview=false", csv);
      setNotice(`Imported: ${result.enrolled} enrolled, ${result.already_enrolled} already enrolled, ${result.pending} pending signup or number linking.`);
      setPreview(null); setCsv(""); setRevision((value) => value + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to import CSV."); }
    finally { setBusy(false); }
  }

  return <details className="mt-4 rounded-2xl border border-white/25 p-4">
    <summary className="cursor-pointer font-semibold text-white">Enroll students · Upload CSV</summary>
    <p className="mt-3 text-sm text-white/80">Upload a CSV with a <strong>matriculation_number</strong> column. Registered students are enrolled immediately. Others join automatically when they link the same number.</p>
    <a download="course-roster-template.csv" href="data:text/csv;charset=utf-8,matriculation_number%0AU2345678A%0AU2345679B%0A"
      className="mt-3 inline-block text-sm font-semibold text-white underline">Download CSV template</a>
    <label className="mt-4 block text-sm text-white">Choose roster CSV (up to 1,000 rows)
      <input type="file" accept=".csv,text/csv" disabled={busy || !accessToken} onChange={(event) => void selectFile(event.target.files?.[0])}
        className="mt-2 block w-full rounded-xl border border-white/25 p-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:px-3 file:py-2" />
    </label>
    {busy && <p role="status" className="mt-2 text-sm text-white/80">Processing roster…</p>}
    {preview && <div className="mt-4 space-y-3">
      <p className="text-sm text-white"><strong>{filename}</strong>: {preview.total} unique students · {preview.enrolled} ready to enroll · {preview.already_enrolled} enrolled · {preview.pending} pending.</p>
      {preview.duplicates > 0 && <p className="text-xs text-white/80">{preview.duplicates} duplicate rows will be ignored.</p>}
      <div className="max-h-52 overflow-auto"><table className="w-full text-left text-xs text-white"><thead><tr><th className="p-2">Matriculation number</th><th className="p-2">Status</th></tr></thead><tbody>
        {preview.items.slice(0, 100).map((row) => <tr key={row.matriculation_number} className="border-t border-white/15"><td className="p-2 font-mono">{row.matriculation_number}</td><td className="p-2">{labels[row.status]}</td></tr>)}
      </tbody></table></div>
      {preview.total > 100 && <p className="text-xs text-white/70">Showing the first 100 rows. All {preview.total} will be imported.</p>}
      <p className="text-xs text-white/70">This adds students to this course. Existing enrollments are kept.</p>
      <button type="button" disabled={busy} onClick={() => void importCsv()} className="rounded-xl bg-white/90 px-4 py-2 font-semibold text-sky-950 disabled:opacity-40">Import roster into {courseCode}</button>
    </div>}
    {error && <p role="alert" className="danger-error mt-3 rounded-xl p-3 text-sm">{error}</p>}
    {notice && <p role="status" className="mt-3 text-sm text-white">{notice}</p>}
    <div className="mt-5 border-t border-white/15 pt-3">
      <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold text-white">Uploaded roster ({roster.length})</h3>
        <button type="button" disabled={busy || loading} onClick={() => setRevision((value) => value + 1)} className="text-xs text-white underline">Refresh</button></div>
      {loading ? <p className="mt-2 text-xs text-white/70">Loading roster…</p> : <ul className="mt-2 max-h-52 overflow-auto text-xs text-white/80">
        {roster.map((row) => <li key={row.matriculation_number} className="flex justify-between gap-3 border-t border-white/15 py-2"><span>{row.matriculation_number}{row.name ? ` · ${row.name}` : ""}</span><span>{row.status === "enroll" ? "Not enrolled" : labels[row.status]}</span></li>)}
        {!roster.length && <li>No CSV roster imported yet.</li>}
      </ul>}
    </div>
  </details>;
}
