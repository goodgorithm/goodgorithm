import assert from "node:assert/strict";
import { test } from "node:test";

import { buildAttachments, type AttachmentSource } from "../src/attachments";

const DID = "did:plc:ibf6ehn7ba3va4jyqhzx6vv3";

function bskyRow(embed: unknown, labels: unknown = null): AttachmentSource {
  return {
    source: "bluesky",
    author_id: DID,
    bluesky_embed: embed,
    mastodon_media: null,
    mastodon_card: null,
    mastodon_sensitive: null,
    bluesky_labels: labels,
  };
}

function mastodonRow(
  media: unknown = null,
  card: unknown = null,
  sensitive: boolean | null = null,
): AttachmentSource {
  return {
    source: "mastodon",
    author_id: "fosstodon.org/someone",
    bluesky_embed: null,
    mastodon_media: media,
    mastodon_card: card,
    mastodon_sensitive: sensitive,
    bluesky_labels: null,
  };
}

// --- Bluesky images (real shape, captured from production) ---

test("bluesky image with aspectRatio", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.images",
      images: [
        {
          alt: "Real Estate Gujarat Training",
          image: {
            ref: { $link: "bafkreihkdhzelfqeomrdx2we476eacogh2uvlddgcnrbu4mkwhnms52osa" },
            $type: "blob",
            mimeType: "image/jpeg",
          },
        },
      ],
    }),
  );

  assert.equal(attachments.length, 1);
  assert.deepEqual(attachments[0], {
    kind: "image",
    thumbnailUrl:
      "https://cdn.bsky.app/img/feed_thumbnail/plain/did:plc:ibf6ehn7ba3va4jyqhzx6vv3/bafkreihkdhzelfqeomrdx2we476eacogh2uvlddgcnrbu4mkwhnms52osa@jpeg",
    fullUrl:
      "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:ibf6ehn7ba3va4jyqhzx6vv3/bafkreihkdhzelfqeomrdx2we476eacogh2uvlddgcnrbu4mkwhnms52osa@jpeg",
    alt: "Real Estate Gujarat Training",
    width: null,
    height: null,
  });
});

test("bluesky image with aspectRatio present carries width/height", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.images",
      images: [
        {
          alt: "",
          image: { ref: { $link: "bafkreignajqth3gc3zqczivpfikgxogbvcyibbswta2guashnxfo3w23jy" } },
          aspectRatio: { width: 510, height: 528 },
        },
      ],
    }),
  );

  assert.equal(attachments[0]?.kind, "image");
  if (attachments[0]?.kind === "image") {
    assert.equal(attachments[0].width, 510);
    assert.equal(attachments[0].height, 528);
    assert.equal(attachments[0].alt, ""); // empty string, not null
  }
});

test("bluesky image alt can be null (real production data has both)", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.images",
      images: [{ alt: null, image: { ref: { $link: "bafkreitest" } } }],
    }),
  );

  assert.equal(attachments[0]?.kind, "image");
  if (attachments[0]?.kind === "image") {
    assert.equal(attachments[0].alt, null);
  }
});

// --- Bluesky external / link card ---

test("bluesky external embed with empty description", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.external",
      external: {
        uri: "https://www.mercurynews.com/2026/08/08/drones-spotted/",
        thumb: { ref: { $link: "bafkreibjiakr52hkql4nuiq5ezyo5nvmqec3t5fgr4r72xgjvtz2do2py4" } },
        title: "2 drones spotted flying over German military base",
        description: "",
      },
    }),
  );

  assert.deepEqual(attachments, [
    {
      kind: "link",
      url: "https://www.mercurynews.com/2026/08/08/drones-spotted/",
      title: "2 drones spotted flying over German military base",
      description: null, // "" normalized to null
      thumbnailUrl:
        "https://cdn.bsky.app/img/feed_thumbnail/plain/did:plc:ibf6ehn7ba3va4jyqhzx6vv3/bafkreibjiakr52hkql4nuiq5ezyo5nvmqec3t5fgr4r72xgjvtz2do2py4@jpeg",
      providerName: null,
    },
  ]);
});

test("bluesky external embed with a non-http(s) uri is dropped", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.external",
      external: { uri: "javascript:alert(1)", title: "nope" },
    }),
  );
  assert.deepEqual(attachments, []);
});

// --- Bluesky quote posts ---

test("bluesky quote of a real post builds a permalink", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.record",
      record: {
        cid: "bafyreie25lnxb35zt4ppydwcgrlw4vgkirbhe5hvtt5kbadrxnhxtmlgwe",
        uri: "at://did:plc:7gtqafwrxxrqfjeq5vgjauir/app.bsky.feed.post/3msljo7hyxc2o",
      },
    }),
  );

  assert.deepEqual(attachments, [
    { kind: "quote", url: "https://bsky.app/profile/did:plc:7gtqafwrxxrqfjeq5vgjauir/post/3msljo7hyxc2o" },
  ]);
});

test("bluesky quote of a non-post collection (e.g. a list) is skipped", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.record",
      record: { cid: "x", uri: "at://did:plc:abc/app.bsky.graph.list/xyz" },
    }),
  );
  assert.deepEqual(attachments, []);
});

// --- recordWithMedia (nesting verified against a real row) ---

test("recordWithMedia with images: media images + quote link, in that order", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.recordWithMedia",
      media: {
        $type: "app.bsky.embed.images",
        images: [{ alt: "a fig basket", image: { ref: { $link: "bafkreie6o5pfpns2hm5p5hmp5rzxfeoxfq6t6gy6jdh7whvcfbfoq4t3g4" } } }],
      },
      record: {
        $type: "app.bsky.embed.record",
        record: { cid: "bafyreiat3ejaxh4d5nrbrk7lwonczhhqt3ci3pnnevh72mgo5ogplw5jsu", uri: "at://did:plc:manzlgiqq2xg23us37wcy6df/app.bsky.feed.post/3msloq6tgrc2f" },
      },
    }),
  );

  assert.equal(attachments.length, 2);
  assert.equal(attachments[0]?.kind, "image");
  assert.deepEqual(attachments[1], {
    kind: "quote",
    url: "https://bsky.app/profile/did:plc:manzlgiqq2xg23us37wcy6df/post/3msloq6tgrc2f",
  });
});

test("recordWithMedia with external media", () => {
  const { attachments } = buildAttachments(
    bskyRow({
      $type: "app.bsky.embed.recordWithMedia",
      media: {
        $type: "app.bsky.embed.external",
        external: { uri: "https://example.com/article", title: "An article" },
      },
      record: {
        $type: "app.bsky.embed.record",
        record: { cid: "x", uri: "at://did:plc:abc/app.bsky.feed.post/xyz" },
      },
    }),
  );

  assert.equal(attachments.length, 2);
  assert.equal(attachments[0]?.kind, "link");
  assert.equal(attachments[1]?.kind, "quote");
});

// --- unrecognized / no embed ---

test("unrecognized embed $type returns no attachments", () => {
  const { attachments } = buildAttachments(bskyRow({ $type: "app.bsky.embed.video", video: {} }));
  assert.deepEqual(attachments, []);
});

test("no embed at all returns no attachments", () => {
  const { attachments } = buildAttachments(bskyRow(null));
  assert.deepEqual(attachments, []);
});

// --- Mastodon media + card (real shapes) ---

test("mastodon image media_attachment", () => {
  const { attachments } = buildAttachments(
    mastodonRow([
      {
        type: "image",
        url: "https://cdn.fosstodon.org/cache/media_attachments/files/117/original/e372bdcbd962f24c.jpg",
        preview_url: "https://cdn.fosstodon.org/cache/media_attachments/files/117/small/e372bdcbd962f24c.jpg",
        description: "Looking down from a 29th floor balcony",
      },
    ]),
  );

  assert.deepEqual(attachments, [
    {
      kind: "image",
      thumbnailUrl: "https://cdn.fosstodon.org/cache/media_attachments/files/117/small/e372bdcbd962f24c.jpg",
      fullUrl: "https://cdn.fosstodon.org/cache/media_attachments/files/117/original/e372bdcbd962f24c.jpg",
      alt: "Looking down from a 29th floor balcony",
      width: null,
      height: null,
    },
  ]);
});

test("mastodon card with an image", () => {
  const { attachments } = buildAttachments(
    mastodonRow(null, {
      url: "https://jmduke.com/posts/secondhand-time.html",
      title: "Secondhand Time",
      description: "It is rare that I review a book before I finish it.",
      image: "https://media.hachyderm.io/cache/preview_cards/images/052/c48f581a405f9c82.jpg",
      provider_name: "Applied Cartography",
    }),
  );

  assert.deepEqual(attachments, [
    {
      kind: "link",
      url: "https://jmduke.com/posts/secondhand-time.html",
      title: "Secondhand Time",
      description: "It is rare that I review a book before I finish it.",
      thumbnailUrl: "https://media.hachyderm.io/cache/preview_cards/images/052/c48f581a405f9c82.jpg",
      providerName: "Applied Cartography",
    },
  ]);
});

test("mastodon card with image: null (confirmed real, ~13% of cards)", () => {
  const { attachments } = buildAttachments(
    mastodonRow(null, {
      url: "https://ku.bz/zJkxP7NL_",
      title: "Senior Configuration Engineer",
      image: null,
      provider_name: "",
    }),
  );

  assert.equal(attachments[0]?.kind, "link");
  if (attachments[0]?.kind === "link") {
    assert.equal(attachments[0].thumbnailUrl, null);
    assert.equal(attachments[0].providerName, null); // "" normalized to null
  }
});

test("mastodon non-image media types (video/gifv) are skipped for now", () => {
  const { attachments } = buildAttachments(
    mastodonRow([{ type: "video", url: "https://example.com/v.mp4", preview_url: "https://example.com/v.jpg" }]),
  );
  assert.deepEqual(attachments, []);
});

// --- sensitive flag ---

test("sensitive: mastodon flag true", () => {
  assert.equal(buildAttachments(mastodonRow(null, null, true)).sensitive, true);
});

test("sensitive: mastodon flag explicitly false", () => {
  assert.equal(buildAttachments(mastodonRow(null, null, false)).sensitive, false);
});

test("sensitive: mastodon flag missing/null", () => {
  assert.equal(buildAttachments(mastodonRow(null, null, null)).sensitive, false);
});

test("sensitive: bluesky labels present", () => {
  const result = buildAttachments(bskyRow(null, { values: [{ val: "porn" }] }));
  assert.equal(result.sensitive, true);
});

test("sensitive: bluesky labels empty array", () => {
  const result = buildAttachments(bskyRow(null, { values: [] }));
  assert.equal(result.sensitive, false);
});

test("sensitive: bluesky labels missing entirely", () => {
  const result = buildAttachments(bskyRow(null, null));
  assert.equal(result.sensitive, false);
});

test("sensitive: malformed labels shape does not throw", () => {
  // values as a string instead of an array - Jetstream relays whatever a
  // client sent with no schema validation, this must not crash the query.
  assert.doesNotThrow(() => buildAttachments(bskyRow(null, { values: "not-an-array" })));
  assert.equal(buildAttachments(bskyRow(null, { values: "not-an-array" })).sensitive, false);
});
