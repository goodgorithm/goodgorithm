#!/usr/bin/env node
// Regenerates web/src/api/types.generated.ts from api/src/types.ts.
//
// Not a live shared package (npm workspaces or a `file:` dependency) --
// api/'s Railway service has rootDirectory scoped to /api (RAILPACK
// builder), so a live cross-directory dependency at build time was
// genuinely uncertain to actually build there. This sidesteps that
// entirely: by the time either service's build runs, the file it needs
// already exists inside its own directory. Run this after changing
// api/src/types.ts; CI fails if the committed output is stale (see
// .github/workflows/ci.yml).
//
// Usage: node scripts/sync-api-types.mjs

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const sourcePath = path.join(repoRoot, "api/src/types.ts");
const outputPath = path.join(repoRoot, "web/src/api/types.generated.ts");

const source = readFileSync(sourcePath, "utf8");

const banner = `// GENERATED FILE -- do not hand-edit.
//
// Mirrors api/src/types.ts, the canonical source for what api/'s HTTP
// responses actually return. Regenerate after changing that file:
//
//   node scripts/sync-api-types.mjs
//
// CI fails the build if this file doesn't match what regenerating right
// now would produce (see .github/workflows/ci.yml) -- if you see that
// failure, you changed api/'s types and forgot to run the command above.

`;

writeFileSync(outputPath, banner + source);
console.log(`wrote ${path.relative(repoRoot, outputPath)} from ${path.relative(repoRoot, sourcePath)}`);
