import type { FastifyInstance } from "fastify";

import { buildAttachments } from "../attachments";
import { fetchFeed } from "../db";
import { decodeCursor, encodeCursor, type Cursor } from "../pagination";
import { buildPermalink } from "../permalink";

const feedQuerySchema = {
  querystring: {
    type: "object",
    properties: {
      limit: { type: "integer", minimum: 1, maximum: 100, default: 20 },
      cursor: { type: "string" },
    },
  },
} as const;

interface FeedQuery {
  limit?: number;
  cursor?: string;
}

export async function feedRoute(app: FastifyInstance): Promise<void> {
  app.get<{ Querystring: FeedQuery }>(
    "/feed",
    { schema: feedQuerySchema },
    async (request, reply) => {
      const limit = request.query.limit ?? 20;

      let cursor: Cursor | null = null;
      if (request.query.cursor) {
        try {
          cursor = decodeCursor(request.query.cursor);
        } catch {
          return reply.code(400).send({ error: "invalid cursor" });
        }
      }

      // fetch one extra row to know if a next page exists, without a second query
      const rows = await fetchFeed(limit + 1, cursor);
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
            author: {
              display_name: row.mastodon_display_name,
              avatar_url: row.mastodon_avatar_url,
            },
            scores: {
              sentiment: row.sentiment_score,
              topicality: row.topicality_score,
              base: row.base_score,
              rank: row.rank_score,
            },
            attachments,
            sensitive,
          };
        }),
        next_cursor,
      };
    },
  );
}
