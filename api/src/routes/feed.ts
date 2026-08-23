import type { FastifyInstance } from "fastify";

import { buildAttachments } from "../attachments";
import { buildAuthor } from "../author";
import { fetchFeed } from "../db";
import { decodeCursor, encodeCursor, type Cursor } from "../pagination";
import { buildPermalink } from "../permalink";
import { CATEGORIES } from "../types";

// See the wiki's Configuration page. minimum stays hardcoded at 1 - not a
// tunable, just the structural floor for "a page of posts" to mean anything.
const FEED_LIMIT_MAX = Number(process.env.FEED_LIMIT_MAX ?? 100);
const FEED_LIMIT_DEFAULT = Number(process.env.FEED_LIMIT_DEFAULT ?? 20);

const feedQuerySchema = {
  querystring: {
    type: "object",
    properties: {
      limit: { type: "integer", minimum: 1, maximum: FEED_LIMIT_MAX, default: FEED_LIMIT_DEFAULT },
      cursor: { type: "string" },
      category: { type: "string", enum: CATEGORIES },
    },
  },
} as const;

interface FeedQuery {
  limit?: number;
  cursor?: string;
  category?: string;
}

export async function feedRoute(app: FastifyInstance): Promise<void> {
  app.get<{ Querystring: FeedQuery }>(
    "/feed",
    { schema: feedQuerySchema },
    async (request, reply) => {
      const limit = request.query.limit ?? FEED_LIMIT_DEFAULT;

      let cursor: Cursor | null = null;
      if (request.query.cursor) {
        try {
          cursor = decodeCursor(request.query.cursor);
        } catch {
          return reply.code(400).send({ error: "invalid cursor" });
        }
      }

      const category = request.query.category ?? null;

      // fetch one extra row to know if a next page exists, without a second query
      const rows = await fetchFeed(limit + 1, cursor, category);
      const hasNext = rows.length > limit;
      const page = hasNext ? rows.slice(0, limit) : rows;
      const last = page[page.length - 1];

      const next_cursor =
        hasNext && last ? encodeCursor({ rank_score: last.rank_score, id: last.id }) : null;

      return {
        posts: page.map((row) => {
          const { attachments, sensitive } = buildAttachments(row);
          return {
            id: row.id,
            source: row.source,
            author_id: row.author_id,
            text: row.text,
            created_at: row.created_at,
            entities: row.entities ?? [],
            permalink: buildPermalink(row),
            author: buildAuthor(row),
            scores: {
              sentiment: row.sentiment_score,
              topicality: row.topicality_score,
              base: row.base_score,
              rank: row.rank_score,
            },
            pipeline_version: row.pipeline_version,
            attachments,
            sensitive,
            category: row.category,
          };
        }),
        next_cursor,
      };
    },
  );
}
