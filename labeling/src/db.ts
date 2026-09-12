import postgres from "postgres";

import type { Attachment, Category, Label, LabelingPost, PostWithLabels, QuoteContent, Study } from "./types";

// Same instance every other service connects to (DATABASE_URL), just a
// dedicated `labeling` schema within it -- see the add_labeling_schema
// migration. No new DB technology, no new pooling story.
const DB_POOL_MAX_SIZE = Number(process.env.DB_POOL_MAX_SIZE ?? 5);
const sql = postgres(process.env.DATABASE_URL!, { max: DB_POOL_MAX_SIZE });

interface StudyRow {
  id: string;
  slug: string;
  name: string;
  categories: Category[];
  created_at: Date;
}

export async function listStudies(): Promise<Study[]> {
  const rows = await sql<StudyRow[]>`
    SELECT id, slug, name, categories, created_at FROM labeling.studies ORDER BY created_at
  `;
  return rows.map((r) => ({ ...r, created_at: r.created_at.toISOString() }));
}

export async function getStudyBySlug(slug: string): Promise<Study | null> {
  const rows = await sql<StudyRow[]>`
    SELECT id, slug, name, categories, created_at FROM labeling.studies WHERE slug = ${slug}
  `;
  if (rows.length === 0) return null;
  const r = rows[0];
  return { ...r, created_at: r.created_at.toISOString() };
}

type PostFilter = "unreviewed" | "flagged" | "all";

interface PostWithLabelsRow {
  id: string;
  study_id: string;
  source: string | null;
  rank_score: number | null;
  original_created_at: Date | null;
  text: string;
  hashtags: string[];
  attachments: Attachment[] | null;
  quote_content: QuoteContent | null;
  batch: string | null;
  created_at: Date;
  ai_category: string | null;
  maintainer_category: string | null;
  maintainer_flag: boolean | null;
  maintainer_notes: string | null;
}

// Both "latest ai label" and "latest maintainer label" are DISTINCT ON
// lateral-equivalent lookups -- done here as two LEFT JOIN LATERALs rather
// than a window function, since we only ever need the single latest row per
// reviewer, not a ranked list.
function postsQuery(studyId: string, filter: PostFilter) {
  const filterClause =
    filter === "unreviewed"
      ? sql`AND ml.category IS NULL`
      : filter === "flagged"
        ? sql`AND ml.taxonomy_flag IS TRUE`
        : sql``;

  return sql<PostWithLabelsRow[]>`
    SELECT p.id, p.study_id, p.source, p.rank_score, p.original_created_at, p.text,
           p.hashtags, p.attachments, p.quote_content, p.batch, p.created_at,
           al.category AS ai_category,
           ml.category AS maintainer_category,
           ml.taxonomy_flag AS maintainer_flag,
           ml.notes AS maintainer_notes
    FROM labeling.posts p
    LEFT JOIN LATERAL (
      SELECT category FROM labeling.labels
      WHERE post_id = p.id AND reviewer = 'ai'
      ORDER BY created_at DESC LIMIT 1
    ) al ON true
    LEFT JOIN LATERAL (
      SELECT category, taxonomy_flag, notes FROM labeling.labels
      WHERE post_id = p.id AND reviewer = 'maintainer'
      ORDER BY created_at DESC LIMIT 1
    ) ml ON true
    WHERE p.study_id = ${studyId}
    ${filterClause}
    ORDER BY p.created_at
  `;
}

function toPostWithLabels(r: PostWithLabelsRow): PostWithLabels {
  return {
    id: r.id,
    study_id: r.study_id,
    source: r.source as LabelingPost["source"],
    rank_score: r.rank_score,
    original_created_at: r.original_created_at?.toISOString() ?? null,
    text: r.text,
    hashtags: r.hashtags,
    attachments: r.attachments,
    quote_content: r.quote_content,
    batch: r.batch,
    created_at: r.created_at.toISOString(),
    ai_label: r.ai_category ? { category: r.ai_category } : null,
    maintainer_label:
      r.maintainer_category != null
        ? { category: r.maintainer_category, taxonomy_flag: r.maintainer_flag ?? false, notes: r.maintainer_notes ?? "" }
        : null,
  };
}

export async function listPosts(studyId: string, filter: PostFilter): Promise<PostWithLabels[]> {
  const rows = await postsQuery(studyId, filter);
  return rows.map(toPostWithLabels);
}

export interface NewPost {
  source: string | null;
  rank_score: number | null;
  original_created_at: string | null;
  text: string;
  hashtags: string[];
  attachments: Attachment[] | null;
  quote_content: QuoteContent | null;
  batch: string | null;
  ai_category: string;
}

// Each new candidate gets its post row plus an immediate reviewer='ai'
// label row carrying the AI-drafted suggestion -- replaces the old
// artifact's "rebuild the whole HTML file, re-embed JSON, republish" flow
// with a plain insert.
export async function insertPosts(studyId: string, posts: NewPost[]): Promise<number> {
  if (posts.length === 0) return 0;
  return sql.begin(async (tx) => {
    let inserted = 0;
    for (const p of posts) {
      const [row] = await tx<{ id: string }[]>`
        INSERT INTO labeling.posts
          (study_id, source, rank_score, original_created_at, text, hashtags, attachments, quote_content, batch)
        VALUES (${studyId}, ${p.source}, ${p.rank_score}, ${p.original_created_at}, ${p.text},
                ${p.hashtags}, ${p.attachments ? tx.json(p.attachments) : null},
                ${p.quote_content ? tx.json(p.quote_content) : null}, ${p.batch})
        RETURNING id
      `;
      await tx`
        INSERT INTO labeling.labels (post_id, reviewer, category)
        VALUES (${row.id}, 'ai', ${p.ai_category})
      `;
      inserted++;
    }
    return inserted;
  });
}

export interface LabelSubmission {
  category: string;
  taxonomy_flag: boolean;
  notes: string;
}

// Always an INSERT, never an UPDATE -- every correction stays in
// labeling.labels, giving the table a free audit trail (see the
// add_labeling_schema migration's header comment).
export async function submitLabel(postId: string, submission: LabelSubmission): Promise<Label> {
  const [row] = await sql<Label[]>`
    INSERT INTO labeling.labels (post_id, reviewer, category, taxonomy_flag, notes)
    VALUES (${postId}, 'maintainer', ${submission.category}, ${submission.taxonomy_flag}, ${submission.notes})
    RETURNING id, post_id, reviewer, category, taxonomy_flag, notes, created_at
  `;
  return row;
}

export interface ExportRow {
  id: string;
  source: string | null;
  batch: string | null;
  text: string;
  category: string;
  taxonomy_flag: boolean;
  notes: string;
  labelled_at: Date;
}

export async function exportLabelled(studyId: string): Promise<ExportRow[]> {
  return sql<ExportRow[]>`
    SELECT p.id, p.source, p.batch, p.text, ml.category, ml.taxonomy_flag, ml.notes, ml.created_at AS labelled_at
    FROM labeling.posts p
    JOIN LATERAL (
      SELECT category, taxonomy_flag, notes, created_at FROM labeling.labels
      WHERE post_id = p.id AND reviewer = 'maintainer'
      ORDER BY created_at DESC LIMIT 1
    ) ml ON true
    WHERE p.study_id = ${studyId}
    ORDER BY p.created_at
  `;
}

export interface DatabaseCheckResult {
  reachable: boolean;
  latencyMs: number;
  error: string | null;
}

const HEALTH_CHECK_TIMEOUT_MS = Number(process.env.HEALTH_CHECK_TIMEOUT_MS ?? 3000);

export async function checkDatabaseConnection(): Promise<DatabaseCheckResult> {
  const start = Date.now();
  try {
    await Promise.race([
      sql`SELECT 1`,
      new Promise((_, reject) => setTimeout(() => reject(new Error("health check timeout")), HEALTH_CHECK_TIMEOUT_MS)),
    ]);
    return { reachable: true, latencyMs: Date.now() - start, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[labeling] database health check failed:", message);
    return { reachable: false, latencyMs: Date.now() - start, error: message };
  }
}

export async function close(): Promise<void> {
  await sql.end();
}
