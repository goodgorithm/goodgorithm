import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchFeed } from "./client";
import type { Category } from "./types";
import { clearCursor, loadCursor, saveCursor } from "../lib/feedCursor";

export function useFeed(category: Category) {
  // Per-category, not a single shared counter: resetting "Kindness &
  // Community" back to the top shouldn't also force "Technology" to the
  // top the next time you switch to it - each category's reset state is
  // independent.
  const [resetGenerations, setResetGenerations] = useState<Record<string, number>>({});
  const generation = resetGenerations[category] ?? 0;

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
    queryKey: ["feed", category, generation],
    queryFn: ({ pageParam }: { pageParam: string | null }) => fetchFeed(pageParam, undefined, category),
    initialPageParam: initialCursor,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });

  useEffect(() => {
    const lastPage = query.data?.pages.at(-1);
    if (lastPage) saveCursor(category, lastPage.next_cursor);
  }, [query.data, category]);

  const resetToTop = () => {
    clearCursor(category);
    setResetGenerations((prev) => ({ ...prev, [category]: generation + 1 }));
  };

  return { ...query, resumed, resetToTop };
}
