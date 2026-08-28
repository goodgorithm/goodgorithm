// The /v1/feed response shape the SHIPPED Android app depends on, frozen at
// git tag android-v0.1.0 (Play Closed Testing, versionCode 1). The app's
// web/src/api/client.ts does zero runtime validation, so any field the
// current API drops or type-changes breaks every tester with no hotfix
// path. tests/android-contract.test.ts asserts a freshly-built FeedPost
// still conforms to this.
//
// Derived by hand from `web/src/api/types.generated.ts @ android-v0.1.0`
// (which is `banner + api/src/types.ts`). Re-freeze on every store release:
// see web/android/RELEASE.md "Cutting a new store build".
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
    tag: "android-v0.1.0",
    versionCode: 1,
    derivedFrom: "web/src/api/types.generated.ts @ android-v0.1.0",
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
    category: "string|null",
  },

  FeedPostAuthor: {
    display_name: "string|null",
    avatar_url: "string|null",
    emojis: "CustomEmoji[]",
  },

  FeedPostScores: {
    sentiment: "number",
    topicality: "number",
    base: "number",
    rank: "number",
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
  },

  QuoteContent: {
    __union: "status",
    available: {
      author: "QuoteAuthor",
      text: "string",
      createdAt: "string|null",
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
