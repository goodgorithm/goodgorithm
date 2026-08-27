import type { Category, FeedResponse } from "./types";

// The default cold-load /v1/feed request, kicked off by an inline <script>
// in index.html *before* this bundle downloads and parses (see that file
// and the wiki's Web Internals page). useFeed adopts the in-flight promise
// for its first page, so the API round-trip runs in parallel with the JS
// download/parse instead of strictly after it.
declare global {
  interface Window {
    __feedBootstrap?: { promise: Promise<FeedResponse> };
  }
}

// The category the inline script pre-fetches. Must stay equal to
// useCategoryParam.ts's DEFAULT_CATEGORY: the inline script hardcodes the
// same value into its URL and only pre-fetches when the page URL carries
// no ?category= param at all.
const BOOTSTRAP_CATEGORY: Category = "arts_culture";

// Hands back the pre-started feed promise exactly once, and only for the
// query whose first page it actually matches: the default category with
// no resume cursor. Every other call -- a different category, a persisted
// cursor, a later page, or no inline script at all -- gets null and the
// caller falls back to a normal fetch. Consuming clears
// window.__feedBootstrap so a later refetch can never reuse a stale
// response.
export function consumeFeedBootstrap(
  category: Category | null,
  cursor: string | null,
): Promise<FeedResponse> | null {
  if (cursor !== null || category !== BOOTSTRAP_CATEGORY) return null;
  const bootstrap = window.__feedBootstrap;
  if (!bootstrap) return null;
  delete window.__feedBootstrap;
  return bootstrap.promise;
}
