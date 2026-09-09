import type { Category } from "../api/types";

function storageKey(category: Category | null): string {
  return `goodgorithm:feedCursor:${category ?? "all"}`;
}

// Real inflow is a few thousand posts/hour, so a resumed cursor goes stale
// fast - past this window we'd rather show fresh top-of-feed content than
// tunnel the user back into old content.
const EXPIRY_MS = 3 * 60 * 60 * 1000;

// Post ids the current session has already shown, stored next to the
// cursor so a reload/resume inside EXPIRY_MS can seed Feed.tsx's dedup
// Set - api/'s rank_score-keyset pagination can hand back a post it
// already served once the background re-ranking shifts scores between
// page fetches, and the in-memory Set alone is empty on a fresh load.
// Capped to the most recent: only a handful of positions ever re-cross,
// and this bounds the localStorage blob (~9KB at 250).
const MAX_SEEN_IDS = 250;

interface StoredCursor {
  cursor: string;
  seenIds?: string[];
  savedAt: number;
}

function readStored(category: Category | null): StoredCursor | null {
  try {
    const key = storageKey(category);
    const raw = localStorage.getItem(key);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as StoredCursor;
    if (Date.now() - parsed.savedAt > EXPIRY_MS) {
      localStorage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function loadCursor(category: Category | null): string | null {
  const parsed = readStored(category);
  return parsed && typeof parsed.cursor === "string" ? parsed.cursor : null;
}

// The ids Feed.tsx should treat as already-seen when resuming this
// category. Empty when nothing is stored, the entry has expired, or the
// blob is malformed - resuming without a seed is the safe fallback.
export function loadSeenIds(category: Category | null): string[] {
  const parsed = readStored(category);
  return parsed && Array.isArray(parsed.seenIds) ? parsed.seenIds : [];
}

export function saveCursor(
  category: Category | null,
  cursor: string | null,
  seenIds: string[] = [],
): void {
  try {
    const key = storageKey(category);
    if (!cursor) {
      localStorage.removeItem(key);
      return;
    }
    const value: StoredCursor = {
      cursor,
      seenIds: seenIds.slice(-MAX_SEEN_IDS),
      savedAt: Date.now(),
    };
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage unavailable (private mode, quota) - resuming is best-effort
  }
}

export function clearCursor(category: Category | null): void {
  try {
    localStorage.removeItem(storageKey(category));
  } catch {
    // ignore
  }
}
