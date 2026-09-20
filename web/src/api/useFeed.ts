import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchFeed } from "./client";
import { consumeFeedBootstrap } from "./feedBootstrap";
import { clearCursor, loadCursor, loadSeenIds, saveCursor } from "../lib/feedCursor";

export function useFeed() {
  const [generation, setGeneration] = useState(0);

  // Recomputed whenever the reset generation changes - NOT frozen at
  // mount, so a "Back to top" reset actually starts clean instead of
  // reusing the cursor that was loaded on first mount.
  const initialCursor = useMemo(
    () => (generation === 0 ? loadCursor() : null),
    [generation],
  );
  const resumed = initialCursor !== null;

  // Post ids already shown before a reload/resume, fed to Feed.tsx so its
  // dedup Set already knows them - the in-memory Set is rebuilt from the
  // loaded pages only, so without this a resumed session can re-render a
  // post the live re-ranking shifted back across the cursor. Only on a
  // real resume (generation 0); a "Back to top" starts clean.
  const carriedSeenIds = useMemo(
    () => (generation === 0 ? loadSeenIds() : []),
    [generation],
  );

  const query = useInfiniteQuery({
    queryKey: ["feed", generation],
    // First page adopts the request the inline <script> in index.html
    // already started, when it matches (no resume cursor). Everything
    // else -- later pages, resumes, refetches -- goes straight to
    // fetchFeed. consumeFeedBootstrap is one-shot, so a retry after a
    // failed adopt falls through here too.
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      (pageParam === initialCursor ? consumeFeedBootstrap(pageParam) : null) ??
      fetchFeed(pageParam),
    initialPageParam: initialCursor,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });

  useEffect(() => {
    const pages = query.data?.pages ?? [];
    const lastPage = pages.at(-1);
    if (!lastPage) return;
    // Merge the ids a prior resumed session carried in with this
    // session's loaded pages, newest last so saveCursor's cap keeps the
    // most recent. carriedSeenIds is [] after a "Back to top", so a reset
    // session's stored set is just its own pages.
    const seenIds = [
      ...new Set([
        ...carriedSeenIds,
        ...pages.flatMap((p) => p.posts.map((post) => post.id)),
      ]),
    ];
    saveCursor(lastPage.next_cursor, seenIds);
  }, [query.data, carriedSeenIds]);

  const resetToTop = () => {
    clearCursor();
    setGeneration((prev) => prev + 1);
  };

  return { ...query, resumed, carriedSeenIds, resetToTop };
}
