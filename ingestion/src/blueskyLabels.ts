import WebSocket from "ws";
import { blockAuthor, deleteBySourceId } from "./db";
import { parseNumberEnv } from "./env";

const MOD_BSKY_LABELS_URL = "wss://mod.bsky.app/xrpc/com.atproto.label.subscribeLabels";

// Shared with bluesky.ts's connection to the Jetstream firehose.
const BLUESKY_RECONNECT_BASE_MS = parseNumberEnv("BLUESKY_RECONNECT_BASE_MS", 5000);
const BLUESKY_RECONNECT_MAX_MS = parseNumberEnv("BLUESKY_RECONNECT_MAX_MS", 60000);

// Bluesky's own global label values -- see the wiki's Bluesky Protocol
// page. Env-overridable so a new label value can be added without a
// redeploy; processing/src/content_filter.py hand-mirrors this same set
// for a separate check and won't pick up a non-default value here
// automatically -- see the wiki's Configuration page.
const BLUESKY_ADULT_LABEL_VALUES = new Set(
  (process.env.BLUESKY_ADULT_LABEL_VALUES ?? "porn,sexual,graphic-media,nudity")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean),
);

// Bluesky's "marks the account as automated" label -- see the wiki's
// Bluesky Protocol page. Targets the account, not a post, so it's routed
// into blocked_authors (parseAccountTarget/blockAuthor below) rather than
// a one-off post deletion.
const BLUESKY_BOT_LABEL_VALUE = process.env.BLUESKY_BOT_LABEL_VALUE ?? "bot";

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
// excluded; there's no row left to "undo."
export function isExcludedLabel(label: Label): boolean {
  return !label.neg && BLUESKY_ADULT_LABEL_VALUES.has(label.val);
}

export function isBotLabel(label: Label): boolean {
  return !label.neg && label.val === BLUESKY_BOT_LABEL_VALUE;
}

// at://{did} -> did; null for anything else. An account-level label's uri
// is the bare repo-authority AT-URI form (see the wiki's Bluesky Protocol
// page), distinct from parsePostTarget's 3-segment shape above.
export function parseAccountTarget(uri: string): string | null {
  if (!uri.startsWith("at://")) return null;
  const rest = uri.slice("at://".length);
  if (!rest || rest.includes("/")) return null;
  return rest;
}

// Frame/payload shape below (`op`, `#info`, `#labels`, `seq`-based
// resumption) is AT Protocol's generic event-stream framing -- see the
// wiki's Bluesky Protocol page.
export function startBlueskyLabelIngestion(): void {
  if (process.env.DISABLE_LABEL_FILTER) {
    console.log("[bluesky-labels] disabled via DISABLE_LABEL_FILTER");
    return;
  }

  let delay = BLUESKY_RECONNECT_BASE_MS;
  let lastSeq: number | undefined;
  // @atcute/cbor is ESM-only; ingestion/ compiles to CommonJS, and tsc
  // downlevels a plain `import()` into a require() that can't load ESM.
  // `new Function` hides the call from that transform so Node performs a
  // real import() instead. Tracked upstream: microsoft/TypeScript#43329.
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
      delay = BLUESKY_RECONNECT_BASE_MS;
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
          if (isBotLabel(label)) {
            const did = parseAccountTarget(label.uri);
            if (!did) continue;
            await blockAuthor("bluesky", did, `mod.bsky.app "bot" label from ${label.src}`);
            console.log(`[bluesky-labels] "bot" from ${label.src} on account ${did} -> blocked`);
            continue;
          }

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
        delay = Math.min(delay * 2, BLUESKY_RECONNECT_MAX_MS);
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
