import WebSocket from "ws";
import { insertPost } from "./db";

const JETSTREAM_URL =
  "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post";

const RECONNECT_BASE_MS = 5_000;
const RECONNECT_MAX_MS = 60_000;

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
    };
  };
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
      const text = record.text?.trim() ?? "";
      if (!text) return;

      // only ingest English posts — pipeline models are English-only
      const langs = record.langs ?? [];
      if (langs.length > 0 && !langs.includes("en")) return;

      try {
        await insertPost({
          source: "bluesky",
          source_id: `${event.did}/${event.commit.rkey}`,
          author_id: event.did,
          text,
          lang: langs[0] ?? null,
          created_at: record.createdAt ? new Date(record.createdAt) : new Date(),
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
