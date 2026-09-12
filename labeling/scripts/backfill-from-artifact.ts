// One-time import of an existing labelled dataset (originally the Civic
// Tone Review self-publishing Artifact's embedded JSON state) into
// labeling.{studies,posts,labels}. Generic over the input shape below, not
// hardcoded to that one dataset, so it's reusable if another external
// export ever needs importing the same way -- but it's still a one-off
// migration tool, not something the running service calls.
//
// Usage: DATABASE_URL=... npx tsx scripts/backfill-from-artifact.ts \
//   <path-to-json> <study-slug> <study-name>
//
// Input JSON: an array of { id, source, rank_score, created_at, text,
// ai_label, human_label, taxonomy_flag, notes }. This shape predates
// hashtags/attachments/quote_content -- those come in null/empty for every
// backfilled row, a known and accepted gap in the historical data.

import "dotenv/config";
import { readFileSync } from "node:fs";

import postgres from "postgres";

const CATEGORIES: Record<string, { label: string; color: string }> = {
  "non-political": { label: "Non-political", color: "#8A8578" },
  "civic-neutral": { label: "Civic-neutral", color: "#5E7FA0" },
  "civic-news": { label: "Civic-news", color: "#6E6BA0" },
  "civic-warm": { label: "Civic-warm", color: "#B4832E" },
  "advocacy-charged": { label: "Advocacy-charged", color: "#8B5FA3" },
  "outrage-mockery": { label: "Outrage-mockery", color: "#B5563C" },
};

interface ArtifactRow {
  id: string;
  source: string;
  rank_score: number;
  created_at: string;
  text: string;
  ai_label: string | null;
  human_label: string | null;
  taxonomy_flag: boolean;
  notes: string;
  batch?: string;
}

async function main(): Promise<void> {
  const [, , jsonPath, slug, name] = process.argv;
  if (!jsonPath || !slug || !name) {
    console.error("usage: backfill-from-artifact.ts <path-to-json> <study-slug> <study-name>");
    process.exit(1);
  }
  if (!process.env.DATABASE_URL) {
    console.error("DATABASE_URL is required");
    process.exit(1);
  }

  const rows: ArtifactRow[] = JSON.parse(readFileSync(jsonPath, "utf-8"));
  const categoriesUsed = new Set([...rows.map((r) => r.ai_label), ...rows.map((r) => r.human_label)].filter(Boolean));
  const categoryDefs = [...categoriesUsed].map((id) => ({
    id,
    label: CATEGORIES[id as string]?.label ?? id,
    color: CATEGORIES[id as string]?.color ?? "#6B665D",
  }));

  const sql = postgres(process.env.DATABASE_URL);
  try {
    const [study] = await sql<{ id: string }[]>`
      INSERT INTO labeling.studies (slug, name, categories)
      VALUES (${slug}, ${name}, ${sql.json(categoryDefs)})
      ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
      RETURNING id
    `;

    let posted = 0;
    let labelled = 0;
    for (const row of rows) {
      const [post] = await sql<{ id: string }[]>`
        INSERT INTO labeling.posts (study_id, source, rank_score, original_created_at, text, batch)
        VALUES (${study.id}, ${row.source}, ${row.rank_score}, ${row.created_at}, ${row.text}, ${row.batch ?? "backfill"})
        RETURNING id
      `;
      posted++;

      if (row.ai_label) {
        await sql`INSERT INTO labeling.labels (post_id, reviewer, category) VALUES (${post.id}, 'ai', ${row.ai_label})`;
      }
      if (row.human_label) {
        await sql`
          INSERT INTO labeling.labels (post_id, reviewer, category, taxonomy_flag, notes)
          VALUES (${post.id}, 'maintainer', ${row.human_label}, ${row.taxonomy_flag}, ${row.notes})
        `;
        labelled++;
      }
    }

    console.log(`study "${slug}": ${posted} posts inserted, ${labelled} with a maintainer label`);
  } finally {
    await sql.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
