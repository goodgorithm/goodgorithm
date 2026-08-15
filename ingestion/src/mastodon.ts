import { insertPost } from "./db";

// Deliberately verified individually before adding, not just picked from a
// "popular instances" list: many well-known instances (mastodon.social
// itself, infosec.exchange, scholar.social, mastodon.art) have disabled
// unauthenticated access to /api/v1/timelines/public (a per-instance admin
// toggle), so a candidate has to actually respond with real data before it
// belongs here. fosstodon.org/hachyderm.io are both tech-leaning; the rest
// were chosen to add topical diversity rather than more of the same --
// sciences.social (Science & Discovery), journa.host (journalism), and
// three general-purpose instances (mstdn.social, mas.to, mastodon.world,
// universeodon.com). Explicitly NOT added despite showing up on general
// "popular instances" lists: mstdn.party -- a random sample of its public
// timeline surfaced genuinely concerning sexualized content involving
// minors, so it fails this project's moderation bar outright regardless of
// volume/topic fit (Content Policy wiki page: "we'd rather exclude too
// much than too little").
const INSTANCES = [
  "fosstodon.org",
  "hachyderm.io",
  "sciences.social",
  "journa.host",
  "universeodon.com",
  "mstdn.social",
  "mas.to",
  "mastodon.world",
];

const POLL_INTERVAL_MS = 30_000;
const REQUEST_TIMEOUT_MS = 10_000;
const USER_AGENT = "Goodgorithm/0.1 (https://github.com/goodgorithm)";

interface MastodonStatus {
  id: string;
  account: { acct: string; discoverable: boolean | null; indexable: boolean | null; created_at: string | null };
  content: string;
  language: string | null;
  created_at: string;
  visibility: string;
}

// Mastodon's two related, distinct opt-out signals for a public account:
// `discoverable` (opted into in-instance discovery -- profile directory,
// "who to follow" recommendations, added 3.1.0) and `indexable` ("allows
// indexing by search engines", added ~4.2/4.3 -- the more literal match for
// "don't index/reuse my posts externally", which is exactly what a
// timeline-polling aggregator like this one does). `public` visibility is
// not consent for reuse (issue #25's research: the fediverse's documented
// norm, and the recurring friction other aggregator tools -- Awakari,
// Contentnation.net, Mnemo.social -- have hit is specifically about
// consent, not about algorithmic ranking itself). Respect either opt-out.
// Live-sampled both polled instances 2026-08-13: indexable=false is
// actually the *more* common signal (58-60% of posts) and frequently
// diverges from discoverable, so checking only one would miss a lot of
// explicit opt-outs. `noindex` (the account-settings field this maps to
// user-facing) is only exposed via the authenticated verify_credentials
// endpoint, not reachable from this unauthenticated polling architecture.
//
// Both fields are nullable per Mastodon's docs (older accounts, or remote
// accounts an instance hasn't fully cached federated data for, may not have
// them set) -- treat null/undefined as opted-in, only an explicit `false`
// excludes a post, so this can't silently start dropping posts if a field
// is ever absent from a response.
export function isDiscoverable(account: { discoverable: boolean | null; indexable: boolean | null }): boolean {
  return account.discoverable !== false && account.indexable !== false;
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

// Block-level tags whose boundaries genuinely separate distinct chunks of
// text (paragraphs, line breaks, list items) - these need to leave a space
// behind so adjacent chunks don't run together into one word.
const BLOCK_TAGS = /<\/?(p|br|div|li|ul|ol|blockquote)\b[^>]*>/gi;

// Bridgy Fed (and possibly other bridges/clients) sometimes wrap a
// genuinely truncated display string ("openai.com/index/unders...") in a
// plain anchor whose href is the real, full URL - unlike the
// invisible/ellipsis-span pattern stripHtml already handles (issue #22),
// there's no second span carrying the untruncated remainder, so the real
// URL only exists in the href attribute (confirmed against real
// production content, issue #42). Substitute the href before generic
// tag-stripping runs, so the emitted text carries a working link instead
// of a dead-end fragment. Scoped to anchors with no nested tags in their
// visible text - hashtag/mention anchors always wrap a nested <span>
// (see the reconstruction below), so this never touches those.
export function resolveTruncatedLinks(html: string): string {
  return html.replace(/<a\s+([^>]*)>([^<]*(?:\.\.\.|…))<\/a>/gi, (match, attrs: string) => {
    const hrefMatch = /href="([^"]*)"/i.exec(attrs);
    return hrefMatch ? hrefMatch[1] : match;
  });
}

export function stripHtml(html: string): string {
  // Mastodon splits a single token (a URL, a hashtag) across multiple
  // adjacent inline <span>/<a> elements purely for its own client-side
  // truncation UI - e.g. a URL's visible text arrives as
  // <span class="invisible">https://www.</span><span class="ellipsis">example.com/a</span><span class="invisible">/b</span>,
  // which must be concatenated with NO separator to reconstruct the real
  // URL. Stripping every tag to a space (as this used to do) corrupted
  // exactly that: "https://www. example.com/a /b" (confirmed on production
  // - issue #22). So this strips in two passes: block tags first (with a
  // separating space), then everything else - now purely inline markup -
  // with no separator at all.
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
    if (!isDiscoverable(status.account)) continue;

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
        // Promoted out of raw_json into its own column (issue #44) --
        // network_detector.py's coordinated-bot-network clustering needs
        // this for every Mastodon row, and extracting it from raw_json at
        // query time timed out at the full ~220k-row Mastodon population.
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
      INSTANCES.map((instance) => pollInstance(instance, sinceId))
    );
  }

  poll();
  setInterval(poll, POLL_INTERVAL_MS);
}
