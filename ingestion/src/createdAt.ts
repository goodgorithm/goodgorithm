// The earlier of a post's source-declared timestamp and the time we observed
// it -- Bluesky's own sortAt rule (min(createdAt, indexedAt)). Both
// networks' declared timestamps can be in the future: Bluesky's createdAt is
// client-declared and never overridden by the PDS, and a federated Mastodon
// status carries its origin server's clock. raw_posts.created_at drives
// recency decay and 24h retention downstream, so an uncapped future value
// would keep full recency until its claimed time and never be cleaned up.
// A backdated value (an import, a migration) is kept as-is. The original
// declared value stays in raw_json. A missing or unparseable declared value
// falls back to the observed time.
export function capCreatedAt(declared: string | null | undefined, observed: Date): Date {
  if (!declared) return observed;
  const parsed = new Date(declared);
  if (Number.isNaN(parsed.getTime())) return observed;
  return parsed < observed ? parsed : observed;
}
