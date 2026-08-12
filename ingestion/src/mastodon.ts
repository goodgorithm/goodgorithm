import { insertPost } from "./db";

const INSTANCES = ["fosstodon.org", "hachyderm.io"];

const POLL_INTERVAL_MS = 30_000;
const REQUEST_TIMEOUT_MS = 10_000;
const USER_AGENT = "Goodgorithm/0.1 (https://github.com/goodgorithm)";

interface MastodonStatus {
  id: string;
  account: { acct: string };
  content: string;
  language: string | null;
  created_at: string;
  visibility: string;
}

// The common named entities Mastodon's HTML actually emits, plus numeric
// (decimal and hex) entities - no dependency for this small, bounded
// parsing job, matching web/'s existing hand-rolled markdown subset.
const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
};

function decodeHtmlEntities(text: string): string {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, entity: string) => {
    if (entity[0] === "#") {
      const codePoint =
        entity[1] === "x" || entity[1] === "X" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
      return Number.isNaN(codePoint) ? match : String.fromCodePoint(codePoint);
    }
    return NAMED_ENTITIES[entity] ?? match;
  });
}

export function stripHtml(html: string): string {
  return decodeHtmlEntities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
}

async function pollInstance(
  instance: string,
  sinceId: Map<string, string>
): Promise<void> {
  const url = new URL(`https://${instance}/api/v1/timelines/public`);
  url.searchParams.set("limit", "40");
  url.searchParams.set("only_media", "false");
  const since = sinceId.get(instance);
  if (since) url.searchParams.set("since_id", since);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    console.error(`[mastodon:${instance}] fetch error:`, (err as Error).message);
    return;
  }

  if (!response.ok) {
    console.error(`[mastodon:${instance}] HTTP ${response.status}`);
    return;
  }

  const statuses = (await response.json()) as MastodonStatus[];
  if (!statuses.length) return;

  sinceId.set(instance, statuses[0].id);

  let inserted = 0;
  for (const status of statuses) {
    if (status.visibility !== "public") continue;
    // only English posts
    if (status.language && status.language !== "en") continue;

    const text = stripHtml(status.content);
    if (!text) continue;

    try {
      await insertPost({
        source: "mastodon",
        source_id: `${instance}/${status.id}`,
        author_id: `${instance}/${status.account.acct}`,
        text,
        lang: status.language,
        created_at: new Date(status.created_at),
        raw_json: status,
      });
      inserted++;
    } catch (err) {
      console.error(`[mastodon:${instance}] insert error:`, err);
    }
  }

  if (inserted > 0) {
    console.log(`[mastodon:${instance}] inserted ${inserted} posts`);
  }
}

export function startMastodonIngestion(): void {
  const sinceId = new Map<string, string>();

  async function poll() {
    await Promise.allSettled(
      INSTANCES.map((instance) => pollInstance(instance, sinceId))
    );
  }

  poll();
  setInterval(poll, POLL_INTERVAL_MS);
}
