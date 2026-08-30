import { insertPost } from "./db";
import { parseNumberEnv } from "./env";

// Which instances to poll, and why each one is trusted, is documented on
// the wiki's Mastodon page -- a new candidate should go through the same
// checks described there before being added here.
const DEFAULT_INSTANCES = [
  "fosstodon.org",
  "hachyderm.io",
  "sciences.social",
  "journa.host",
  "universeodon.com",
  "mstdn.social",
  "mas.to",
  "mastodon.world",
];
const MASTODON_INSTANCES = (process.env.MASTODON_INSTANCES ?? DEFAULT_INSTANCES.join(","))
  .split(",")
  .map((v) => v.trim())
  .filter(Boolean);

const MASTODON_POLL_INTERVAL_MS = parseNumberEnv("MASTODON_POLL_INTERVAL_MS", 30000);
const MASTODON_REQUEST_TIMEOUT_MS = parseNumberEnv("MASTODON_REQUEST_TIMEOUT_MS", 10000);
const USER_AGENT = "Goodgorithm/0.1 (https://github.com/goodgorithm)";

// Per-instance poll outcome, for the status endpoint -- sinceId
// (pagination) is the only other thing that persists across cycles.
// Without this, a single instance going fully silent would be invisible
// short of reading logs, since both Bluesky connections and all 8
// Mastodon instances funnel into the same heartbeat counter.
export interface InstanceStatus {
  lastSuccessAt: Date | null;
  lastErrorAt: Date | null;
  lastError: string | null;
}
const instanceStatus = new Map<string, InstanceStatus>();

export function getInstanceStatus(): Record<string, InstanceStatus> {
  return Object.fromEntries(instanceStatus);
}

export function recordSuccess(instance: string): void {
  const status = instanceStatus.get(instance) ?? { lastSuccessAt: null, lastErrorAt: null, lastError: null };
  status.lastSuccessAt = new Date();
  instanceStatus.set(instance, status);
}

export function recordError(instance: string, message: string): void {
  const status = instanceStatus.get(instance) ?? { lastSuccessAt: null, lastErrorAt: null, lastError: null };
  status.lastErrorAt = new Date();
  status.lastError = message;
  instanceStatus.set(instance, status);
}

interface MastodonStatus {
  id: string;
  account: { acct: string; discoverable: boolean | null; indexable: boolean | null; created_at: string | null };
  content: string;
  language: string | null;
  created_at: string;
  visibility: string;
}

// Respects Mastodon's discoverable/indexable account opt-outs -- public
// visibility isn't consent for reuse. Null/undefined counts as opted-in;
// only an explicit false excludes. See the wiki's Mastodon page.
export function isDiscoverable(account: { discoverable: boolean | null; indexable: boolean | null }): boolean {
  return account.discoverable !== false && account.indexable !== false;
}

// Bridgy Fed federates Bluesky (and web/RSS) content into the fediverse as
// accounts on *.brid.gy. Skipped here so it never enters raw_posts: it's an
// unsampled second intake of Bluesky content that bypasses
// BLUESKY_SAMPLE_RATE, the knob balancing Bluesky volume against
// processing/'s throughput. suppressed_domains carries 'brid.gy' as the
// authoritative filter (it also catches a post that merely *links* there);
// this is just a cheap ingestion-time early-out. See issue #140.
const BRIDGE_HOST = "brid.gy";

export function isBridgedAccount(acct: string): boolean {
  const at = acct.lastIndexOf("@");
  if (at === -1) return false; // local account -- no bridge host to match
  const host = acct.slice(at + 1).toLowerCase();
  return host === BRIDGE_HOST || host.endsWith(`.${BRIDGE_HOST}`);
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

// "AT&amp;T &#8211; est. 1885" -> "AT&T – est. 1885"
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

// Block-level tags whose boundaries genuinely separate distinct chunks of
// text (paragraphs, line breaks, list items) - these need to leave a space
// behind so adjacent chunks don't run together into one word.
const BLOCK_TAGS = /<\/?(p|br|div|li|ul|ol|blockquote)\b[^>]*>/gi;

// Recovers a bridged truncated link's real href before generic
// tag-stripping runs -- see the wiki's Mastodon page (Status content
// rendering quirks). Scoped to anchors with no nested tags in their
// visible text, since hashtag/mention anchors always wrap a nested <span>.
export function resolveTruncatedLinks(html: string): string {
  return html.replace(/<a\s+([^>]*)>([^<]*(?:\.\.\.|…))<\/a>/gi, (match, attrs: string) => {
    const hrefMatch = /href="([^"]*)"/i.exec(attrs);
    return hrefMatch ? hrefMatch[1] : match;
  });
}

export function stripHtml(html: string): string {
  // Two-pass strip (block tags get a separating space, inline tags don't)
  // to avoid corrupting Mastodon's split-token truncation markup -- see
  // the wiki's Mastodon page (Status content rendering quirks).
  const withResolvedLinks = resolveTruncatedLinks(html);
  const withBlockBreaks = withResolvedLinks.replace(BLOCK_TAGS, " ");
  const withoutTags = withBlockBreaks.replace(/<[^>]+>/g, "");
  return decodeHtmlEntities(withoutTags).replace(/\s+/g, " ").trim();
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
      signal: AbortSignal.timeout(MASTODON_REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    console.error(`[mastodon:${instance}] fetch error:`, (err as Error).message);
    recordError(instance, (err as Error).message);
    return;
  }

  if (!response.ok) {
    console.error(`[mastodon:${instance}] HTTP ${response.status}`);
    recordError(instance, `HTTP ${response.status}`);
    return;
  }

  recordSuccess(instance);
  const statuses = (await response.json()) as MastodonStatus[];
  if (!statuses.length) return;

  sinceId.set(instance, statuses[0].id);

  let inserted = 0;
  for (const status of statuses) {
    if (status.visibility !== "public") continue;
    // only English posts
    if (status.language && status.language !== "en") continue;
    if (!isDiscoverable(status.account)) continue;
    if (isBridgedAccount(status.account.acct)) continue;

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
        // Own column, not read from raw_json -- a deliberate performance
        // trade-off required for bot detection's clustering query.
        mastodon_account_created_at: status.account.created_at ? new Date(status.account.created_at) : null,
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
      MASTODON_INSTANCES.map((instance) => pollInstance(instance, sinceId))
    );
  }

  poll();
  setInterval(poll, MASTODON_POLL_INTERVAL_MS);
}
