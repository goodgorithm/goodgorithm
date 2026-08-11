import { useEffect, useRef, useState } from "react";

import { useFeed } from "../api/useFeed";
import type { Category } from "../api/types";
import { CategorySelector } from "./CategorySelector";
import styles from "./Feed.module.css";
import { FeedEmpty, FeedError, FeedLoading } from "./FeedStatus";
import { PostCard } from "./PostCard";

export function Feed() {
  const [category, setCategory] = useState<Category | null>(null);
  const { data, error, isPending, isFetchingNextPage, fetchNextPage, hasNextPage, resumed, resetToTop } =
    useFeed(category);
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

  return (
    <div>
      <CategorySelector selected={category} onSelect={setCategory} />
      {isPending && <FeedLoading />}
      {error && <FeedError message={error.message} />}
      {!isPending && !error && posts.length === 0 && <FeedEmpty />}
      {!isPending && !error && resumed && (
        <button type="button" className={styles.backToTop} onClick={resetToTop}>
          ↑ Back to top
        </button>
      )}
      {posts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}
      <div ref={sentinelRef} />
      {isFetchingNextPage && <FeedLoading />}
    </div>
  );
}
