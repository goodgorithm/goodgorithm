import { useEffect, useRef } from "react";

import { useFeed } from "../api/useFeed";
import styles from "./Feed.module.css";
import { FeedEmpty, FeedError, FeedLoading } from "./FeedStatus";
import { PostCard } from "./PostCard";

export function Feed() {
  const { data, error, isPending, isFetchingNextPage, fetchNextPage, hasNextPage, resumed, resetToTop } =
    useFeed();
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

  if (isPending) return <FeedLoading />;
  if (error) return <FeedError message={error.message} />;

  const posts = data.pages.flatMap((page) => page.posts);
  if (posts.length === 0) return <FeedEmpty />;

  return (
    <div>
      {resumed && (
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
