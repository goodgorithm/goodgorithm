import WebSocket from "ws";
import { insertPost } from "./db";

const JETSTREAM_URL =
  "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post";

const RECONNECT_BASE_MS = 5_000;
const RECONNECT_MAX_MS = 60_000;

// Bluesky Jetstream volume (~86,670 posts/hour observed 2026-08-10) vastly
// exceeds processing/'s throughput even after the backlog-aware-sleep fix
// (~7,800-8,570/hour capacity) - keeping every post guarantees an
// ever-deepening backlog where posts age past the 24h retention cutoff
// before processing ever reaches them. Sampling down to a representative
// subset keeps the backlog bounded by design. Default 1.0 (no throttling)
// so nothing changes unless explicitly configured.
const BLUESKY_SAMPLE_RATE = Number(process.env.BLUESKY_SAMPLE_RATE ?? "1.0");

interface JetstreamEvent {
  did: string;
  time_us: number;
  kind: string;
  commit?: {
    operation: string;
    collection: string;
    rkey: string;
    record?: {
      $type: string;
      text?: string;
      createdAt?: string;
      langs?: string[];
      facets?: unknown;
    };
  };
}

interface BlueskyFacet {
  index: { byteStart: number; byteEnd: number };
  features: Array<{ $type?: unknown; uri?: unknown }>;
}

// AT Protocol facet byte ranges are UTF-8 byte offsets into `text`, not JS
// string (UTF-16 code unit) offsets - these diverge for any text with
// multi-byte characters before the facet, so this must operate on real
// UTF-8 bytes (Buffer), not string indices. A poster's own client often
// shows a shortened display string for a long link ("apnews.com/article/
// davi...") while the real target only lives in a facet -- confirmed
// live at real volume in production (issue #42), completely unused until
// now. Processed back-to-front so each earlier byteStart/byteEnd stays
// valid as later replacements change the buffer's length. Only
// substitutes when the visible text doesn't already look like a complete
// URL, to avoid needlessly rewriting already-fine links.
export function resolveFacetLinks(text: string, facets: unknown): string {
  if (!Array.isArray(facets)) return text;

  const linkFacets = (facets as BlueskyFacet[])
    .filter(
      (f): f is BlueskyFacet =>
        typeof f?.index?.byteStart === "number" &&
        typeof f?.index?.byteEnd === "number" &&
        Array.isArray(f.features),
    )
    .map((f) => ({
      index: f.index,
      uri: f.features.find(
        (feat) => feat.$type === "app.bsky.richtext.facet#link" && typeof feat.uri === "string",
      )?.uri as string | undefined,
    }))
    .filter((f): f is { index: BlueskyFacet["index"]; uri: string } => typeof f.uri === "string")
    .sort((a, b) => b.index.byteStart - a.index.byteStart);

  let buf = Buffer.from(text, "utf8");
  for (const facet of linkFacets) {
    const visible = buf.subarray(facet.index.byteStart, facet.index.byteEnd).toString("utf8");
    if (visible.startsWith("http://") || visible.startsWith("https://")) continue;
    buf = Buffer.concat([
      buf.subarray(0, facet.index.byteStart),
      Buffer.from(facet.uri, "utf8"),
      buf.subarray(facet.index.byteEnd),
    ]);
  }
  return buf.toString("utf8");
}

export function startBlueskyIngestion(): void {
  let delay = RECONNECT_BASE_MS;

  function connect() {
    const ws = new WebSocket(JETSTREAM_URL);

    ws.on("open", () => {
      console.log("[bluesky] connected to Jetstream");
      delay = RECONNECT_BASE_MS;
    });

    ws.on("message", async (data) => {
      let event: JetstreamEvent;
      try {
        event = JSON.parse(data.toString()) as JetstreamEvent;
      } catch {
        return;
      }

      if (
        event.kind !== "commit" ||
        event.commit?.operation !== "create" ||
        !event.commit.record
      ) {
        return;
      }

      const record = event.commit.record;
      // Resolve facet-marked links before trimming -- byte offsets are
      // computed against the original, untrimmed text.
      const text = resolveFacetLinks(record.text ?? "", record.facets).trim();
      if (!text) return;

      // only ingest English posts — pipeline models are English-only
      const langs = record.langs ?? [];
      if (langs.length > 0 && !langs.includes("en")) return;

      if (Math.random() >= BLUESKY_SAMPLE_RATE) return;

      try {
        await insertPost({
          source: "bluesky",
          source_id: `${event.did}/${event.commit.rkey}`,
          author_id: event.did,
          text,
          lang: langs[0] ?? null,
          created_at: record.createdAt ? new Date(record.createdAt) : new Date(),
          mastodon_account_created_at: null, // no equivalent concept on Bluesky
          raw_json: event,
        });
      } catch (err) {
        console.error("[bluesky] insert error:", err);
      }
    });

    ws.on("close", () => {
      console.log(`[bluesky] disconnected — reconnecting in ${delay / 1000}s`);
      setTimeout(() => {
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
        connect();
      }, delay);
    });

    ws.on("error", (err) => {
      console.error("[bluesky] WebSocket error:", err.message);
      ws.terminate();
    });
  }

  connect();
}
