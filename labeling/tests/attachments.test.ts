import assert from "node:assert/strict";
import { test } from "node:test";

import { buildAttachments, extractHashtags } from "../src/attachments";

test("extractHashtags pulls hashtags out of post text", () => {
  assert.deepEqual(extractHashtags("Loving this #Sunset in #Arizona today"), ["Sunset", "Arizona"]);
  assert.deepEqual(extractHashtags("no hashtags here"), []);
});

test("buildAttachments parses a Bluesky external-link embed into a link attachment", () => {
  const attachments = buildAttachments({
    source: "bluesky",
    author_id: "did:plc:abc",
    text: "check this out",
    bluesky_embed: {
      $type: "app.bsky.embed.external",
      external: { uri: "https://example.com/article", title: "An article", description: "About things" },
    },
    mastodon_media: null,
    mastodon_card: null,
    quote_content: null,
    generated_thumbnail_url: null,
  });
  assert.equal(attachments.length, 1);
  assert.equal(attachments[0].kind, "link");
  assert.equal((attachments[0] as { url: string }).url, "https://example.com/article");
});

test("buildAttachments parses a Mastodon link card", () => {
  const attachments = buildAttachments({
    source: "mastodon",
    author_id: "user@example.social",
    text: "check this out",
    bluesky_embed: null,
    mastodon_media: null,
    mastodon_card: { url: "https://example.com/post", title: "A post", provider_name: "Example" },
    quote_content: null,
    generated_thumbnail_url: null,
  });
  assert.equal(attachments.length, 1);
  assert.equal(attachments[0].kind, "link");
});

test("buildAttachments returns nothing for a bare-text post with no embed", () => {
  const attachments = buildAttachments({
    source: "bluesky",
    author_id: "did:plc:abc",
    text: "just some text, no links or images",
    bluesky_embed: null,
    mastodon_media: null,
    mastodon_card: null,
    quote_content: null,
    generated_thumbnail_url: null,
  });
  assert.equal(attachments.length, 0);
});
