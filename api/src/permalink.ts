export interface PermalinkSource {
  source: "bluesky" | "mastodon";
  source_id: string;
  mastodon_permalink: string | null;
}

// Bluesky's Jetstream firehose carries no profile/permalink data, but a
// working bsky.app URL is fully constructible from the DID + rkey already in
// source_id. Mastodon's raw_json already has the real permalink from the API.
export function buildPermalink(row: PermalinkSource): string {
  if (row.source === "bluesky") {
    const [did, rkey] = row.source_id.split("/");
    return `https://bsky.app/profile/${did}/post/${rkey}`;
  }
  return row.mastodon_permalink ?? "";
}
