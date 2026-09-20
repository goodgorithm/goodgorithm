import type { FeedResponse } from "./types";

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

// Hands back the pre-started feed promise exactly once, and only for the
// query it actually matches: no resume cursor. Every other call -- a
// persisted cursor, a later page, or no inline script at all -- gets null
// and the caller falls back to a normal fetch. Consuming clears
// window.__feedBootstrap so a later refetch can never reuse a stale
// response.
export function consumeFeedBootstrap(cursor: string | null): Promise<FeedResponse> | null {
  if (cursor !== null) return null;
  const bootstrap = window.__feedBootstrap;
  if (!bootstrap) return null;
  delete window.__feedBootstrap;
  return bootstrap.promise;
}
