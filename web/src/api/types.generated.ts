// GENERATED FILE -- do not hand-edit.
//
// Mirrors api/src/types.ts, the canonical source for what api/'s HTTP
// responses actually return. Regenerate after changing that file:
//
//   node scripts/sync-api-types.mjs
//
// CI fails the build if this file doesn't match what regenerating right
// now would produce (see .github/workflows/ci.yml) -- if you see that
// failure, you changed api/'s types and forgot to run the command above.

// The canonical shapes api/'s HTTP responses actually return. Single source
// of truth for this service - other route/parsing modules import from here
// instead of defining these shapes inline or scattered across files.
//
// web/'s copy (web/src/api/types.generated.ts) is generated from this file
// by scripts/sync-api-types.mjs, not hand-duplicated - see that script and
// CLAUDE.md's Versioning & migration section for why (Railway's rootDirectory
// scoping on api/'s service ruled out a live shared package - a generated,
// committed file avoids both services' builds ever needing to reach outside
// their own directory).

export type Source = "bluesky" | "mastodon";

// The fixed 4-category taxonomy assigned by processing/'s category_model.py
// (a trained classifier, with taxonomy.py's keyword matcher as a fallback).
// See CLAUDE.md's Category filtering section for why these 4. Deliberately
// no DB CHECK constraint enforcing this set (see processed_posts.category
// in supabase/migrations/0005_add_category.sql) - a stricter constraint
// would make the taxonomy harder to extend, not easier. See the wiki's API
// Internals page for what happens end to end when this list and the DB
// disagree.
export const CATEGORIES = ["science_technology", "arts_culture", "food_dining", "diaries_daily_life"] as const;

export type Category = (typeof CATEGORIES)[number];

export interface FeedPostScores {
  sentiment: number;
  topicality: number;
  base: number;
  rank: number;
}

// Mastodon's custom-emoji shortcode mechanism - a `:shortcode:` in
// display_name/post text is meant to render as this inline image,
// client-side, per Mastodon's own convention. Bluesky has no equivalent,
// so this is always `[]` for Bluesky posts/authors. Only the two fields
// web/ actually needs to render one - Mastodon's API also returns
// `static_url`/`visible_in_picker`/`category`, none of which apply here
// (no emoji picker exists in this product).
export interface CustomEmoji {
  shortcode: string;
  url: string;
}

export interface FeedPostAuthor {
  display_name: string | null;
  avatar_url: string | null;
  // account.emojis - resolves shortcodes used in display_name. A post's
  // own text uses a separate array (FeedPost.emojis below, from the
  // status's own emojis) - Mastodon models these independently since an
  // account's display name and a specific post can use different custom
  // emoji sets.
  emojis: CustomEmoji[];
}

// Pre-shaped by processing/'s quote_resolver.py at scoring time (batched
// AppView calls, content-filtered before storage) and passed straight
// through here - api/ does no further shaping or network calls of its
// own. "not_found" covers deleted/blocked/detached alike (getPosts, the
// batch endpoint used to resolve these, doesn't distinguish which - only
// per-thread embed views do, and resolving each quote's own thread just
// to get that distinction wasn't worth the extra AppView calls).
export type QuoteContent =
  | {
      status: "available";
      author: { displayName: string | null; handle: string | null; avatarUrl: string | null };
      text: string;
      createdAt: string | null;
    }
  | { status: "unavailable"; reason: "not_found" | "filtered" };

export type Attachment =
  | {
      kind: "image";
      thumbnailUrl: string;
      fullUrl: string;
      alt: string | null;
      width: number | null;
      height: number | null;
    }
  | {
      kind: "link";
      url: string;
      title: string | null;
      description: string | null;
      thumbnailUrl: string | null;
      providerName: string | null;
    }
  | {
      kind: "video";
      playlistUrl: string;
      thumbnailUrl: string | null;
      isGif: boolean;
      width: number | null;
      height: number | null;
    }
  | { kind: "quote"; url: string; content: QuoteContent | null };

export interface FeedPost {
  id: string;
  source: Source;
  author_id: string;
  text: string;
  created_at: string;
  entities: string[];
  permalink: string;
  author: FeedPostAuthor;
  // Resolves shortcodes used in `text` itself - the status's own emojis
  // array, distinct from author.emojis above.
  emojis: CustomEmoji[];
  scores: FeedPostScores;
  // Which pipeline logic produced this post's scores - see CLAUDE.md's
  // Versioning & migration section.
  pipeline_version: string;
  attachments: Attachment[];
  sensitive: boolean;
  category: Category | null;
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface HealthDatabaseStatus {
  reachable: boolean;
  latency_ms: number;
  error?: string | null;
}

export interface HealthConfig {
  rate_limit_max: number;
  rate_limit_time_window: string;
  feed_limit_max: number;
  feed_limit_default: number;
  db_pool_max_size: number;
  health_check_timeout_ms: number;
  feed_query_timeout_ms: number;
}

export interface HealthResponse {
  status: string;
  // Railway's auto-provided commit SHA for the running deployment - see
  // CLAUDE.md's Versioning & migration section. Makes the real, confirmed
  // deploy-skew window between services (railway-deploy.sh deploys
  // sequentially, tolerating partial failure) observable instead of
  // invisible. "unknown" outside Railway (e.g. local dev).
  version: string;
  timestamp: string;
  database: HealthDatabaseStatus;
  // Public, safe-to-expose config only -- an auditable first-look, not a
  // log replacement. See CLAUDE.md's Service resilience section.
  config: HealthConfig;
}
