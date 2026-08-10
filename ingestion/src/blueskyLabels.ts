import WebSocket from "ws";
import { deleteBySourceId } from "./db";

const MOD_BSKY_LABELS_URL = "wss://mod.bsky.app/xrpc/com.atproto.label.subscribeLabels";

const RECONNECT_BASE_MS = 5_000;
const RECONNECT_MAX_MS = 60_000;

// Bluesky's own moderation-service global label values for adult content
// (com.atproto.label.defs), confirmed 2026-08-11. Bluesky can add more
// over time -- this set, not scattered logic, is the place to update.
// Duplicated by hand in processing/src/content_filter.py -- no shared
// package exists across the TS/Python boundary in this repo.
const ADULT_LABEL_VALUES = new Set(["porn", "sexual", "graphic-media", "nudity"]);

interface Label {
  src: string;
  uri: string;
  val: string;
  neg?: boolean;
  cts: string;
}

interface LabelsPayload {
  seq: number;
  labels: Label[];
}

interface FrameHeader {
  op: number;
  t?: string;
}

interface InfoPayload {
  name?: string;
  message?: string;
}

// at://{did}/app.bsky.feed.post/{rkey} -> {did, rkey}; null for anything
// that isn't a post-collection AT-URI (e.g. account-level labels).
export function parsePostTarget(uri: string): { did: string; rkey: string } | null {
  if (!uri.startsWith("at://")) return null;
  const parts = uri.slice("at://".length).split("/");
  if (parts.length !== 3 || parts[1] !== "app.bsky.feed.post") return null;
  const [did, , rkey] = parts;
  if (!did || !rkey) return null;
  return { did, rkey };
}

// Retractions (neg: true) are deliberately ignored -- once excluded, stays
// excluded. Direct consequence of "precision over recall" (Decisions Log,
// 2026-08-11), not an oversight: there's nothing to "undo" once the
// matching raw_posts row has already been deleted.
export function isExcludedLabel(label: Label): boolean {
  return !label.neg && ADULT_LABEL_VALUES.has(label.val);
}

export function startBlueskyLabelIngestion(): void {
  if (process.env.DISABLE_LABEL_FILTER) {
    console.log("[bluesky-labels] disabled via DISABLE_LABEL_FILTER");
    return;
  }

  let delay = RECONNECT_BASE_MS;
  let lastSeq: number | undefined;
  // @atcute/cbor is a pure-ESM package ("type": "module", no CJS build) --
  // ingestion/ compiles to CommonJS and runs via plain `node dist/index.js`.
  // A real dynamic import() can load ESM from CJS code, but tsc's
  // CommonJS output downlevels a plain `await import(...)` into a
  // require() wrapped in Promise.resolve() (visible in dist/ output),
  // which still throws ERR_REQUIRE_ESM -- the Promise wrapper doesn't
  // change that require() can never load ESM. Routing the call through
  // `new Function` keeps it as a runtime string, invisible to tsc's
  // static downlevel transform, so Node performs a genuine import()
  // instead. Standard workaround for this specific, well-known
  // TypeScript+Node CJS/ESM interop gap.
  const importEsm = new Function("specifier", "return import(specifier)") as (
    specifier: string,
  ) => Promise<typeof import("@atcute/cbor")>;
  let decodeFirst: typeof import("@atcute/cbor").decodeFirst;

  async function connect() {
    if (!decodeFirst) {
      ({ decodeFirst } = await importEsm("@atcute/cbor"));
    }

    const url = lastSeq !== undefined ? `${MOD_BSKY_LABELS_URL}?cursor=${lastSeq}` : MOD_BSKY_LABELS_URL;
    const ws = new WebSocket(url);

    ws.on("open", () => {
      console.log("[bluesky-labels] connected to labels stream");
      delay = RECONNECT_BASE_MS;
    });

    ws.on("message", async (data) => {
      try {
        // ws delivers binary frames as Buffer, which already satisfies
        // Uint8Array -- no conversion needed. Two consecutive top-level
        // DAG-CBOR values per message: a header, then a payload.
        const buf = data as Buffer;
        const [header, afterHeader] = decodeFirst(buf) as [FrameHeader, Uint8Array];

        if (header.op !== 1) {
          const [errPayload] = decodeFirst(afterHeader) as [
            { error?: string; message?: string },
            Uint8Array,
          ];
          console.error("[bluesky-labels] error frame:", errPayload.error, errPayload.message);
          return;
        }

        if (header.t === "#info") {
          const [info] = decodeFirst(afterHeader) as [InfoPayload, Uint8Array];
          if (info.name === "OutdatedCursor") {
            console.warn("[bluesky-labels] cursor outdated, dropping it:", info.message);
            lastSeq = undefined;
          }
          return;
        }

        if (header.t !== "#labels") return;

        const [payload] = decodeFirst(afterHeader) as [LabelsPayload, Uint8Array];
        lastSeq = payload.seq;

        for (const label of payload.labels) {
          if (!isExcludedLabel(label)) continue;
          const target = parsePostTarget(label.uri);
          if (!target) continue;

          const deleted = await deleteBySourceId("bluesky", `${target.did}/${target.rkey}`);
          console.log(
            `[bluesky-labels] "${label.val}" from ${label.src} on ${label.uri}` +
              (deleted ? " -> deleted" : " (no matching row)"),
          );
        }
      } catch (err) {
        // A bug in this brand-new CBOR/matching path must never crash the
        // whole ingestion process and take the primary Jetstream/Mastodon
        // paths down with it.
        console.error("[bluesky-labels] error handling message:", err);
      }
    });

    ws.on("close", () => {
      console.log(`[bluesky-labels] disconnected — reconnecting in ${delay / 1000}s`);
      setTimeout(() => {
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
        void safeConnect();
      }, delay);
    });

    ws.on("error", (err) => {
      console.error("[bluesky-labels] WebSocket error:", err.message);
      ws.terminate();
    });
  }

  // connect() is async (the dynamic import), so both call sites need a
  // rejection handler -- an uncaught one here would be an unhandled
  // promise rejection, which can crash the process depending on Node's
  // configuration, exactly what the try/catch inside the message handler
  // is already there to prevent.
  async function safeConnect() {
    try {
      await connect();
    } catch (err) {
      console.error("[bluesky-labels] fatal connect error:", err);
    }
  }

  void safeConnect();
}
