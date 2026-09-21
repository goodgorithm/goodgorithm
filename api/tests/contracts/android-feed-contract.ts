// The /v1/feed response shape the SHIPPED Android app depends on, frozen at
// git tag android-v0.2.0 (Play Closed Testing, versionCode 2). The app's
// web/src/api/client.ts does zero runtime validation, so any field the
// current API drops or type-changes breaks every tester with no hotfix
// path. tests/android-contract.test.ts asserts a freshly-built FeedPost
// still conforms to this.
//
// Lists the fields the shipped web/ bundle (same codebase for the PWA and
// this Capacitor build) actually reads, plus a couple (author_id,
// pipeline_version) kept for their standalone audit/debugging value even
// though no UI renders them - not every field api/'s FeedPost carries.
// A field with neither a reader nor that kind of standing value has no
// place in this contract, since api/ dropping it can't break the app; see
// web/'s components (PostCard.tsx, ScoreDetails.tsx, QuoteLink.tsx, etc.)
// for what's read. Re-freeze on every store release: see
// web/android/RELEASE.md "Cutting a new store build".
//
// Field-string grammar for the asserter (tests/contracts/assert-contract.ts):
//   "string" | "number" | "boolean"   primitive, non-null
//   "X|null"                          null allowed, else X
//   "X[]"                             array, each element is X
//   "<TypeName>"                      a key in this object; recurse
//   { __union: "<discriminant>", <value>: {...}, ... }
//                                    pick the sub-shape by value[discriminant];
//                                    unknown discriminant value passes (the
//                                    frozen app degrades gracefully).

export const FEED_CONTRACT = {
  _meta: {
    tag: "android-v0.2.0",
    versionCode: 2,
    derivedFrom: "web/src/api/types.generated.ts @ android-v0.2.0",
  },

  FeedResponse: {
    posts: "FeedPost[]",
    next_cursor: "string|null",
  },

  FeedPost: {
    id: "string",
    source: "string",
    author_id: "string",
    text: "string",
    created_at: "string",
    entities: "string[]",
    permalink: "string",
    author: "FeedPostAuthor",
    emojis: "CustomEmoji[]",
    scores: "FeedPostScores",
    pipeline_version: "string",
    attachments: "Attachment[]",
    sensitive: "boolean",
  },

  FeedPostAuthor: {
    display_name: "string|null",
    avatar_url: "string|null",
    emojis: "CustomEmoji[]",
  },

  FeedPostScores: {
    base: "number",
    rank: "number",
    quality: "number|null",
  },

  CustomEmoji: {
    shortcode: "string",
    url: "string",
  },

  Attachment: {
    __union: "kind",
    image: {
      thumbnailUrl: "string",
      fullUrl: "string",
      alt: "string|null",
      width: "number|null",
      height: "number|null",
    },
    link: {
      url: "string",
      title: "string|null",
      description: "string|null",
      thumbnailUrl: "string|null",
      providerName: "string|null",
    },
    video: {
      playlistUrl: "string",
      thumbnailUrl: "string|null",
      isGif: "boolean",
      width: "number|null",
      height: "number|null",
    },
    quote: {
      url: "string",
      content: "QuoteContent|null",
    },
    reply: {
      url: "string",
      content: "QuoteContent|null",
    },
  },

  QuoteContent: {
    __union: "status",
    available: {
      author: "QuoteAuthor",
      text: "string",
    },
    unavailable: {
      reason: "string",
    },
  },

  QuoteAuthor: {
    displayName: "string|null",
    handle: "string|null",
    avatarUrl: "string|null",
  },
} as const;
