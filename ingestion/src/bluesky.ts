import WebSocket from "ws";
import { insertPost } from "./db";

// Fixed since this connection was first added - no operational need found
// yet to point it at a different Jetstream instance.
const JETSTREAM_URL =
  "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post";

// Shared with blueskyLabels.ts's connection to the labels stream.
const BLUESKY_RECONNECT_BASE_MS = Number(process.env.BLUESKY_RECONNECT_BASE_MS ?? "5000");
const BLUESKY_RECONNECT_MAX_MS = Number(process.env.BLUESKY_RECONNECT_MAX_MS ?? "60000");

// Keeps ingestion volume from outrunning processing/'s throughput. See the
// wiki's Configuration page for tuning guidance.
const BLUESKY_SAMPLE_RATE = Number(process.env.BLUESKY_SAMPLE_RATE ?? "1.0");

// Jetstream event/commit/record shape -- see the wiki's Bluesky Protocol page.
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

// Recovers a post's real link target from its facets when the visible text
// is just a shortened display string -- see the wiki's Bluesky Protocol
// page (Rich text facets). Byte offsets are UTF-8 bytes, not JS string
// indices, so this operates on a Buffer. Processed back-to-front so each
// earlier byteStart/byteEnd stays valid as later substitutions change the
// buffer's length. Skips a facet whose visible text already looks like a
// complete URL, to avoid needlessly rewriting already-fine links.
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
  let delay = BLUESKY_RECONNECT_BASE_MS;

  function connect() {
    const ws = new WebSocket(JETSTREAM_URL);

    ws.on("open", () => {
      console.log("[bluesky] connected to Jetstream");
      delay = BLUESKY_RECONNECT_BASE_MS;
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
        delay = Math.min(delay * 2, BLUESKY_RECONNECT_MAX_MS);
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
