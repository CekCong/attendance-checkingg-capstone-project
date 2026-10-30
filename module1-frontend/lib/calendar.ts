export const CALENDAR_TIMEZONE = "Asia/Singapore";
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// All calendar dates and wall times use Singapore, regardless of the browser's timezone.
export function parseSessionDate(value: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`);
}
export function singaporeDate(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: CALENDAR_TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  return ["year", "month", "day"].map((part) => parts.find((value) => value.type === part)!.value).join("-");
}
export function addDays(day: string, amount: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}
export function weekStart(day: string): string {
  const weekday = new Date(`${day}T12:00:00Z`).getUTCDay();
  return addDays(day, -((weekday + 6) % 7));
}
export function localInstant(day: string, time = "00:00"): string {
  return new Date(`${day}T${time}:00+08:00`).toISOString();
}
export function minutesInDay(date: Date): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: CALENDAR_TIMEZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(date);
  return Number(parts.find((part) => part.type === "hour")!.value) * 60 + Number(parts.find((part) => part.type === "minute")!.value);
}
export function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-SG", { timeZone: CALENDAR_TIMEZONE, hour: "numeric", minute: "2-digit" }).format(parseSessionDate(value));
}
export function recurringDates(start: string, end: string, weekday: number): string[] {
  if (!start || !end || end < start) return [];
  let day = addDays(start, (weekday - ((new Date(`${start}T12:00:00Z`).getUTCDay() + 6) % 7) + 7) % 7);
  const result: string[] = [];
  while (day <= end && result.length < 54) { result.push(day); day = addDays(day, 7); }
  return result;
}
export function semesterOptions(today = singaporeDate()) {
  const year = Number(today.slice(0, 4));
  return Array.from({ length: 4 }, (_, index) => year - 1 + index).flatMap((start) => [1, 2].map((term) => ({
    value: `${start}/${String(start + 1).slice(-2)} Semester ${term}`,
    label: `AY ${start}/${String(start + 1).slice(-2)} · Semester ${term}`,
  })));
}

export type CalendarEvent = { id: string; scheduled_start: string; scheduled_end: string };
export function layoutDay<T extends CalendarEvent>(events: T[], day: string) {
  const dayStart = new Date(localInstant(day)).getTime();
  const dayEnd = new Date(localInstant(addDays(day, 1))).getTime();
  const items = events.map((event) => ({ event,
    start: Math.max(0, (parseSessionDate(event.scheduled_start).getTime() - dayStart) / 60000),
    end: Math.min(1440, (parseSessionDate(event.scheduled_end).getTime() - dayStart) / 60000),
    column: 0, columns: 1,
  })).filter((item) => parseSessionDate(item.event.scheduled_start).getTime() < dayEnd && item.end > item.start)
    .sort((a, b) => a.start - b.start || b.end - a.end);
  let group: typeof items = [];
  let ends: number[] = [];
  let groupEnd = -1;
  function finish() { group.forEach((item) => { item.columns = ends.length; }); group = []; ends = []; }
  for (const item of items) {
    if (item.start >= groupEnd) finish();
    let column = ends.findIndex((end) => end <= item.start);
    if (column < 0) column = ends.length;
    item.column = column;
    ends[column] = item.end;
    groupEnd = Math.max(item.end, ...ends);
    group.push(item);
  }
  finish();
  return items;
}

export function monthDays(day: string): string[] {
  const first = `${day.slice(0, 7)}-01`;
  const start = weekStart(first);
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}
export function addMonths(day: string, amount: number): string {
  const date = new Date(`${day.slice(0, 7)}-01T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + amount);
  return date.toISOString().slice(0, 10);
}
