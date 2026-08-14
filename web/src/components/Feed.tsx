import { useEffect, useMemo, useRef } from "react";

import { useFeed } from "../api/useFeed";
import { CategorySelector } from "./CategorySelector";
import styles from "./Feed.module.css";
import { FeedEmpty, FeedError, FeedLoading } from "./FeedStatus";
import { useCategoryParam } from "../lib/useCategoryParam";
import { relativeFractions, type RelativeFractions } from "../lib/scoreScale";
import { PostCard } from "./PostCard";

const NO_RELATIVE: RelativeFractions = { topicality: 0, base: 0, rank: 0 };

export function Feed() {
  const [category, setCategory] = useCategoryParam();
  const {
    data,
    error,
    isPending,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
    resumed,
    resetToTop,
    refetch,
  } = useFeed(category);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasNextPage) return;

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) fetchNextPage();
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasNextPage, fetchNextPage]);

  const posts = data?.pages.flatMap((page) => page.posts) ?? [];

  // One percentile basis per fetched page (see scoreScale.ts) - computed
  // per page, then merged, so a page already on screen never has its
  // posts' bars recalculated (and silently shift) as later pages load.
  const relativeByPostId = useMemo(() => {
    const merged = new Map<string, RelativeFractions>();
    for (const page of data?.pages ?? []) {
      for (const [id, fractions] of relativeFractions(page.posts)) {
        merged.set(id, fractions);
      }
    }
    return merged;
  }, [data?.pages]);

  return (
    <div>
      <CategorySelector selected={category} onSelect={setCategory} />
      {isPending && <FeedLoading />}
      {error && <FeedError message={error.message} onRetry={refetch} />}
      {!isPending && !error && posts.length === 0 && (
        <FeedEmpty category={category} onShowFullFeed={() => setCategory(null)} />
      )}
      {!isPending && !error && resumed && (
        <button type="button" className={styles.backToTop} onClick={resetToTop}>
          ↑ Back to top
        </button>
      )}
      {posts.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          relative={relativeByPostId.get(post.id) ?? NO_RELATIVE}
        />
      ))}
      <div ref={sentinelRef} />
      {isFetchingNextPage && <FeedLoading />}
    </div>
  );
}
