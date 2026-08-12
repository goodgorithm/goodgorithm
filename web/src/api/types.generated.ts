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

// The fixed 8-category taxonomy assigned by processing/'s taxonomy.py.
// Deliberately no DB CHECK constraint enforcing this set (see
// processed_posts.category in supabase/migrations/0005_add_category.sql) -
// a stricter constraint would make the taxonomy harder to extend, not
// easier, which cuts against this project's migration-friendliness goal.
export const CATEGORIES = [
  "technology",
  "arts_culture",
  "animals",
  "science_discovery",
  "kindness_community",
  "environment_nature",
  "health_recovery",
  "sports_achievement",
] as const;

export type Category = (typeof CATEGORIES)[number];

export interface FeedPostScores {
  sentiment: number;
  topicality: number;
  base: number;
  rank: number;
}

export interface FeedPostAuthor {
  display_name: string | null;
  avatar_url: string | null;
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
  scores: FeedPostScores;
  // Which pipeline logic produced this post's scores - mirrors how
  // sentiment_method already records which sentiment scorer (CNN vs VADER)
  // produced a score. processed_posts.pipeline_version existed as a schema
  // column since the table was created but was never actually written by
  // processing/ or read here until this was wired up (see CLAUDE.md).
  pipeline_version: string;
  attachments: Attachment[];
  sensitive: boolean;
  category: Category | null;
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface HealthResponse {
  status: string;
  // Railway's auto-provided commit SHA for the running deployment - see
  // CLAUDE.md's Versioning & migration section. Makes the real, confirmed
  // deploy-skew window between services (railway-deploy.sh deploys
  // sequentially, tolerating partial failure) observable instead of
  // invisible. "unknown" outside Railway (e.g. local dev).
  version: string;
}
