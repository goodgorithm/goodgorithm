export function FeedLoading() {
  return <p role="status">Loading feed…</p>;
}

export function FeedEmpty() {
  return <p role="status">No posts yet.</p>;
}

// Deliberately never shows stale/cached posts here - a live-ranked feed
// silently serving old data offline would misrepresent itself. See the
// no-runtimeCaching decision in vite.config.ts.
export function FeedError({ message }: { message: string }) {
  return (
    <p role="alert">
      Couldn't load the feed ({message}). Check your connection and try again.
    </p>
  );
}
