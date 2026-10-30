import type { LessonHistoryItem } from "./types";

const STORAGE_PREFIX = "saiv_lesson_history:";

const SEED: LessonHistoryItem[] = [];

function keyFor(email: string) {
  return `${STORAGE_PREFIX}${email.toLowerCase()}`;
}

export function loadLessonHistory(email: string): LessonHistoryItem[] {
  if (typeof window === "undefined") return SEED;
  try {
    const raw = sessionStorage.getItem(keyFor(email));
    if (!raw) {
      sessionStorage.setItem(keyFor(email), JSON.stringify(SEED));
      return SEED;
    }
    const parsed = JSON.parse(raw) as LessonHistoryItem[];
    return Array.isArray(parsed) ? parsed : SEED;
  } catch {
    return SEED;
  }
}

export function saveLessonHistory(email: string, items: LessonHistoryItem[]) {
  sessionStorage.setItem(keyFor(email), JSON.stringify(items));
}

export function appendLessonHistory(email: string, item: LessonHistoryItem) {
  const existing = loadLessonHistory(email).filter((row) => row.id !== item.id);
  const next = [item, ...existing];
  saveLessonHistory(email, next);
  return next;
}
