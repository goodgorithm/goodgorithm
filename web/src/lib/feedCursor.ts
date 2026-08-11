const STORAGE_KEY = "goodgorithm:feedCursor";

// Real inflow is a few thousand posts/hour, so a resumed cursor goes stale
// fast - past this window we'd rather show fresh top-of-feed content than
// tunnel the user back into old content.
const EXPIRY_MS = 3 * 60 * 60 * 1000;

interface StoredCursor {
  cursor: string;
  savedAt: number;
}

export function loadCursor(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as StoredCursor;
    if (Date.now() - parsed.savedAt > EXPIRY_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed.cursor;
  } catch {
    return null;
  }
}

export function saveCursor(cursor: string | null): void {
  try {
    if (!cursor) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    const value: StoredCursor = { cursor, savedAt: Date.now() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // localStorage unavailable (private mode, quota) - resuming is best-effort
  }
}

export function clearCursor(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
