import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchFeed } from "./client";
import { clearCursor, loadCursor, saveCursor } from "../lib/feedCursor";

export function useFeed() {
  const [initialCursor] = useState<string | null>(() => loadCursor());
  const [resumed, setResumed] = useState(initialCursor !== null);
  const [nonce, setNonce] = useState(0);

  const query = useInfiniteQuery({
    queryKey: ["feed", nonce],
    queryFn: ({ pageParam }: { pageParam: string | null }) => fetchFeed(pageParam),
    initialPageParam: nonce === 0 ? initialCursor : null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });

  useEffect(() => {
    const lastPage = query.data?.pages.at(-1);
    if (lastPage) saveCursor(lastPage.next_cursor);
  }, [query.data]);

  const resetToTop = () => {
    clearCursor();
    setResumed(false);
    setNonce((n) => n + 1);
  };

  return { ...query, resumed, resetToTop };
}
