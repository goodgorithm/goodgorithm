import WebSocket from "ws";
import { blockAuthor, deleteBySourceId, getBlockedAuthors, insertPost, isBlockedAuthor } from "./db";
import { parseNumberEnv } from "./env";
import { consumePendingExclusion, markPendingExclusion } from "./pendingExclusions";

// Fixed since this connection was first added - no operational need found
// yet to point it at a different Jetstream instance.
const JETSTREAM_URL =
  "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post";

// Shared with blueskyLabels.ts's connection to the labels stream.
const BLUESKY_RECONNECT_BASE_MS = parseNumberEnv("BLUESKY_RECONNECT_BASE_MS", 5000);
const BLUESKY_RECONNECT_MAX_MS = parseNumberEnv("BLUESKY_RECONNECT_MAX_MS", 60000);

// Keeps ingestion volume from outrunning processing/'s throughput. See the
// wiki's Configuration page for tuning guidance.
const BLUESKY_SAMPLE_RATE = parseNumberEnv("BLUESKY_SAMPLE_RATE", 1.0);

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
  // kind:"account" frames carry no commit -- just the account's current
  // hosting status. Present on the same firehose regardless of
  // wantedCollections.
  account?: {
    active: boolean;
    status?: string;
  };
}

// active:false with one of these statuses means the account's posts have
// stopped resolving on the AppView for good -- taken down by a moderation
// service, self-deleted, or suspended. "deactivated" is deliberately
// absent: it's user-reversible, so a post can come back.
const ACCOUNT_TAKEDOWN_STATUSES = new Set(["takendown", "suspended", "deleted"]);

// A commit with operation "delete" for the post collection carries no
// record -- only the rkey of the now-gone post. Returns the `${did}/${rkey}`
// source_id form, or null for creates/updates and non-post collections.
export function parseDeleteCommit(event: JetstreamEvent): string | null {
  if (event.kind !== "commit") return null;
  const commit = event.commit;
  if (!commit || commit.operation !== "delete" || commit.collection !== "app.bsky.feed.post") {
    return null;
  }
  if (!event.did || !commit.rkey) return null;
  return `${event.did}/${commit.rkey}`;
}

// The DID of an account whose kind:"account" frame reports it as gone (see
// ACCOUNT_TAKEDOWN_STATUSES), or null otherwise. Routed into blocked_authors
// so processing/'s purge_blocked_authors sweep drops its already-ingested
// posts -- an account takedown emits no com.atproto.label event, so neither
// the label stream nor moderation_recheck.py would ever catch it.
export function accountTakedownDid(event: JetstreamEvent): string | null {
  if (event.kind !== "account" || !event.did) return null;
  const account = event.account;
  if (!account || account.active !== false) return null;
  if (!account.status || !ACCOUNT_TAKEDOWN_STATUSES.has(account.status)) return null;
  return event.did;
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

// Connection-health state for the status endpoint -- module-level since
// startBlueskyIngestion() is only ever called once (from index.ts), but a
// closure-local variable wouldn't be reachable from outside it. Not a
// business-logic signal, purely for statusServer.ts to read.
let connected = false;
let connectedAt: Date | null = null;
let lastMessageAt: Date | null = null;
let reconnectDelayMs = BLUESKY_RECONNECT_BASE_MS;

export function getConnectionState() {
  return { connected, connectedAt, lastMessageAt, reconnectDelayMs };
}

export function startBlueskyIngestion(): void {
  let delay = BLUESKY_RECONNECT_BASE_MS;

  function connect() {
    const ws = new WebSocket(JETSTREAM_URL);

    ws.on("open", () => {
      console.log("[bluesky] connected to Jetstream");
      delay = BLUESKY_RECONNECT_BASE_MS;
      connected = true;
      connectedAt = new Date();
      reconnectDelayMs = delay;
    });

    ws.on("message", async (data) => {
      lastMessageAt = new Date();
      let event: JetstreamEvent;
      try {
        event = JSON.parse(data.toString()) as JetstreamEvent;
      } catch {
        return;
      }

      // A post we already ingested was deleted on Bluesky. Drop our copy
      // (processed_posts cascades). A 0-row delete may just mean our own
      // create for this rkey hasn't landed yet -- remember it so the create
      // path skips the insert, symmetric to blueskyLabels.ts.
      const deletedSourceId = parseDeleteCommit(event);
      if (deletedSourceId) {
        try {
          const deleted = await deleteBySourceId("bluesky", deletedSourceId);
          if (deleted === 0) markPendingExclusion(deletedSourceId);
          console.log(
            `[bluesky] delete commit for ${deletedSourceId}` +
              (deleted > 0 ? " -> deleted" : " -> marked pending exclusion (no matching row yet)"),
          );
        } catch (err) {
          console.error("[bluesky] delete handling error:", err);
        }
        return;
      }

      // The post's author was taken down / suspended / deleted their
      // account. Block the DID; processing/'s purge sweep removes their
      // already-ingested posts within its own window.
      const takedownDid = accountTakedownDid(event);
      if (takedownDid) {
        try {
          const status = event.account?.status;
          await blockAuthor("bluesky", takedownDid, `jetstream account ${status}`);
          console.log(`[bluesky] account ${status} for ${takedownDid} -> blocked`);
        } catch (err) {
          console.error("[bluesky] account takedown handling error:", err);
        }
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

      // only ingest English posts — pipeline models are English-only
      const langs = record.langs ?? [];
      if (langs.length > 0 && !langs.includes("en")) return;

      if (Math.random() >= BLUESKY_SAMPLE_RATE) return;

      // Resolve facet-marked links before trimming -- byte offsets are
      // computed against the original, untrimmed text. Runs after the
      // cheap checks above (most messages get dropped by those) since
      // this allocates a buffer per call.
      const text = resolveFacetLinks(record.text ?? "", record.facets).trim();
      if (!text) return;

      const sourceId = `${event.did}/${event.commit.rkey}`;
      // Bluesky's own moderation labeler can react faster than our own
      // insert lands -- if blueskyLabels.ts already tried and failed to
      // delete this exact post, don't insert it at all.
      if (consumePendingExclusion(sourceId)) {
        console.log(`[bluesky] skipped insert for ${sourceId} -- pending exclusion from label stream`);
        return;
      }

      // Skip a still-active blocked author's stream before it hits raw_posts.
      // Silent, like isBridgedAccount -- these accounts post
      // constantly, which is the whole reason to catch them here.
      if (isBlockedAuthor("bluesky", event.did, await getBlockedAuthors())) return;

      try {
        await insertPost({
          source: "bluesky",
          source_id: sourceId,
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
      connected = false;
      connectedAt = null;
      console.log(`[bluesky] disconnected — reconnecting in ${delay / 1000}s`);
      setTimeout(() => {
        delay = Math.min(delay * 2, BLUESKY_RECONNECT_MAX_MS);
        reconnectDelayMs = delay;
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
