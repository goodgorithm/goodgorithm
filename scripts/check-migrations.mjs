#!/usr/bin/env node
// Validates supabase/migrations/ so the CI `supabase db push` step (see
// .github/workflows/ci.yml's migrate-staging / migrate-production jobs)
// stays predictable, and so CLAUDE.md's "schema migrations are
// additive-only" rule is actually enforced rather than just documented.
//
// Checks, in order:
//   1. every file is <14-digit UTC timestamp>_<lower_snake_slug>.sql
//   2. the 14 digits parse as a real calendar datetime (UTC)
//   3. timestamps are strictly increasing in sorted (== chronological) order
//      -- db push applies pending files in version order, so a collision or
//      an out-of-order file is a latent apply-order bug
//   4. no DROP / RENAME / TYPE-narrowing / TRUNCATE unless the file carries
//      a `-- non-additive: <reason>` line acknowledging it
//
// Exit non-zero (with the offending file named) on any failure. No deps, no
// network, no DB -- runs on every push and PR.
//
// Usage: node scripts/check-migrations.mjs

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const migrationsDir = path.join(repoRoot, "supabase/migrations");

const NAME_RE = /^(\d{14})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$/;

// Non-additive DDL that can break a still-running old process mid-deploy
// (see CLAUDE.md's sequential-deploy window). A file doing any of this must
// spell out why and how it's sequenced, on a `-- non-additive:` line.
const NON_ADDITIVE = [
  { re: /\bDROP\s+(COLUMN|TABLE|CONSTRAINT|INDEX|VIEW|SCHEMA|FUNCTION|TRIGGER|TYPE)\b/i, what: "DROP" },
  { re: /\bALTER\s+COLUMN\b[^;]*\bTYPE\b/i, what: "ALTER COLUMN ... TYPE" },
  { re: /\bRENAME\s+(COLUMN|TO|CONSTRAINT)\b/i, what: "RENAME" },
  { re: /\bTRUNCATE\b/i, what: "TRUNCATE" },
];
const ACK_RE = /^--\s*non-additive:\s*\S/m;

// Strip -- line comments and '...' / "..." string literals so a keyword
// inside prose or a seed value never trips the additive check.
function stripNoise(sql) {
  return sql
    .replace(/--[^\n]*/g, "")
    .replace(/'(?:[^']|'')*'/g, "''")
    .replace(/"(?:[^"]|"")*"/g, '""');
}

const errors = [];
const files = readdirSync(migrationsDir).filter((f) => f.endsWith(".sql")).sort();

if (files.length === 0) errors.push("no .sql files found in supabase/migrations/");

let prevStamp = "";
for (const file of files) {
  const m = NAME_RE.exec(file);
  if (!m) {
    errors.push(`${file}: name must be <14-digit-UTC-timestamp>_<lower_snake_slug>.sql`);
    continue;
  }
  const stamp = m[1];
  const [y, mo, d, h, mi, s] = [
    stamp.slice(0, 4), stamp.slice(4, 6), stamp.slice(6, 8),
    stamp.slice(8, 10), stamp.slice(10, 12), stamp.slice(12, 14),
  ].map(Number);
  const dt = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  const roundTrips =
    dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d &&
    dt.getUTCHours() === h && dt.getUTCMinutes() === mi && dt.getUTCSeconds() === s;
  if (!roundTrips) errors.push(`${file}: "${stamp}" is not a real UTC YYYYMMDDHHMMSS datetime`);

  if (prevStamp && stamp <= prevStamp) {
    errors.push(`${file}: timestamp ${stamp} is not strictly after the previous migration (${prevStamp})`);
  }
  prevStamp = stamp;

  const sql = readFileSync(path.join(migrationsDir, file), "utf8");
  const body = stripNoise(sql);
  for (const { re, what } of NON_ADDITIVE) {
    if (re.test(body) && !ACK_RE.test(sql)) {
      errors.push(
        `${file}: contains ${what} but no "-- non-additive: <reason>" line. ` +
          `Additive migrations only, or acknowledge + sequence it (see CLAUDE.md's Versioning & migration section).`,
      );
    }
  }
}

if (errors.length) {
  console.error("migration checks failed:\n" + errors.map((e) => `  - ${e}`).join("\n"));
  process.exit(1);
}
console.log(`migration checks passed (${files.length} files).`);
