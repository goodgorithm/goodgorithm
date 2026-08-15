import type { Category } from "../api/types";

function storageKey(category: Category): string {
  return `goodgorithm:feedCursor:${category}`;
}

// Real inflow is a few thousand posts/hour, so a resumed cursor goes stale
// fast - past this window we'd rather show fresh top-of-feed content than
// tunnel the user back into old content.
const EXPIRY_MS = 3 * 60 * 60 * 1000;

interface StoredCursor {
  cursor: string;
  savedAt: number;
}

export function loadCursor(category: Category): string | null {
  try {
    const key = storageKey(category);
    const raw = localStorage.getItem(key);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as StoredCursor;
    if (Date.now() - parsed.savedAt > EXPIRY_MS) {
      localStorage.removeItem(key);
      return null;
    }
    return parsed.cursor;
  } catch {
    return null;
  }
}

export function saveCursor(category: Category, cursor: string | null): void {
  try {
    const key = storageKey(category);
    if (!cursor) {
      localStorage.removeItem(key);
      return;
    }
    const value: StoredCursor = { cursor, savedAt: Date.now() };
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage unavailable (private mode, quota) - resuming is best-effort
  }
}

export function clearCursor(category: Category): void {
  try {
    localStorage.removeItem(storageKey(category));
  } catch {
    // ignore
  }
}
