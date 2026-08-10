import postgres from "postgres";

import { recordInsert } from "./heartbeat";

const sql = postgres(process.env.DATABASE_URL!, { max: 5 });

export interface RawPost {
  source: "bluesky" | "mastodon";
  source_id: string;
  author_id: string;
  text: string;
  lang: string | null;
  created_at: Date;
  raw_json: unknown;
}

export async function insertPost(post: RawPost): Promise<void> {
  await sql`
    INSERT INTO raw_posts (source, source_id, author_id, text, lang, created_at, raw_json)
    VALUES (
      ${post.source},
      ${post.source_id},
      ${post.author_id},
      ${post.text},
      ${post.lang},
      ${post.created_at},
      ${sql.json(post.raw_json as Parameters<typeof sql.json>[0])}
    )
    ON CONFLICT (source, source_id) DO NOTHING
  `;
  // Query succeeding (even a no-op duplicate skip via ON CONFLICT) is
  // evidence the pipeline is actually connected and functioning - that's
  // the signal the heartbeat cares about, not strictly "a new row landed."
  recordInsert();
}

export async function close(): Promise<void> {
  await sql.end();
}
