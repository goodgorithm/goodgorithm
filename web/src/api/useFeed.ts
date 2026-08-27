import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchFeed } from "./client";
import { consumeFeedBootstrap } from "./feedBootstrap";
import type { Category } from "./types";
import { clearCursor, loadCursor, saveCursor } from "../lib/feedCursor";

export function useFeed(category: Category | null) {
  const categoryKey = category ?? "all";

  // Per-category, not a single shared counter: resetting "Arts & Culture"
  // back to the top shouldn't also force "Science & Technology" to the
  // top the next time you switch to it - each category's reset state is
  // independent.
  const [resetGenerations, setResetGenerations] = useState<Record<string, number>>({});
  const generation = resetGenerations[categoryKey] ?? 0;

  // Recomputed whenever category or that category's reset generation
  // changes - NOT frozen at mount, so switching category actually resumes
  // *that* category's saved cursor instead of reusing whatever cursor was
  // loaded for the category the hook happened to start on.
  const initialCursor = useMemo(
    () => (generation === 0 ? loadCursor(category) : null),
    [category, generation],
  );
  const resumed = initialCursor !== null;

  const query = useInfiniteQuery({
    queryKey: ["feed", categoryKey, generation],
    // First page adopts the request the inline <script> in index.html
    // already started, when it matches (default category, no resume
    // cursor). Everything else -- later pages, other categories, resumes,
    // refetches -- goes straight to fetchFeed. consumeFeedBootstrap is
    // one-shot, so a retry after a failed adopt falls through here too.
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      (pageParam === initialCursor ? consumeFeedBootstrap(category, pageParam) : null) ??
      fetchFeed(pageParam, undefined, category),
    initialPageParam: initialCursor,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });

  useEffect(() => {
    const lastPage = query.data?.pages.at(-1);
    if (lastPage) saveCursor(category, lastPage.next_cursor);
  }, [query.data, category]);

  const resetToTop = () => {
    clearCursor(category);
    setResetGenerations((prev) => ({ ...prev, [categoryKey]: generation + 1 }));
  };

  return { ...query, resumed, resetToTop };
}
