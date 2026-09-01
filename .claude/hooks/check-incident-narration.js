#!/usr/bin/env node
'use strict';

/*
 * PostToolUse (Edit|Write) heuristic guard for CLAUDE.md's documentation policy:
 * comments, module docs, and CLAUDE.md/wiki prose describe current-state
 * behavior only. History -- past bugs, outages, "we tried X", issue-number
 * chains, "used to / initially lacked" -- belongs in git commit messages and
 * closed GitHub issues, not in the tree.
 *
 * This scans ONLY the text a single Edit/Write added, and ONLY comment / prose
 * lines (never code), for incident-narration markers. It is heuristic and
 * NON-BLOCKING: it always exits 0, and on a hit it surfaces a systemMessage to
 * the user plus additionalContext back to the model so the just-written text
 * can be reconsidered in the same turn.
 */

const fs = require('fs');

function readStdin() {
  for (const src of [0, '/dev/stdin']) {
    try {
      const s = fs.readFileSync(src, 'utf8');
      if (s) return s;
    } catch (_) {
      /* try next */
    }
  }
  return '';
}

let payload;
try {
  payload = JSON.parse(readStdin() || '{}');
} catch (_) {
  process.exit(0);
}

const toolInput = payload.tool_input || {};
const filePath = String(toolInput.file_path || '');
if (!filePath) process.exit(0);

// The documentation policy is about this repo's tree. Skip anything outside it
// (scratch files, ~/.claude memory notes) when the project root is known.
const projectDir = process.env.CLAUDE_PROJECT_DIR;
if (projectDir && !filePath.startsWith(projectDir)) process.exit(0);

const base = filePath.split('/').pop();
const isMd = /\.md$/i.test(base);
const isPy = /\.py$/i.test(base);
const isTs = /\.tsx?$/i.test(base);
if (!isMd && !isPy && !isTs) process.exit(0);

// Text this call added: Edit -> new_string, Write -> content. MultiEdit is not
// matched by this hook's matcher, so it is not handled here.
let added = '';
if (typeof toolInput.new_string === 'string') added = toolInput.new_string;
else if (typeof toolInput.content === 'string') added = toolInput.content;
if (!added.trim()) process.exit(0);

const isTest =
  /(^|\/)(tests?|__tests__)\//.test(filePath) ||
  /^test_.*\.py$/.test(base) ||
  /_test\.py$/.test(base) ||
  /\.(test|spec)\.tsx?$/.test(base);

// [label, regex] -- all matched case-insensitively against the prose portion
// of a line. Kept deliberately narrow: these phrasings almost always narrate
// history rather than describe current behavior.
const MARKERS = [
  ['history verb "crashed"', /\bcrash(ed|es|ing)\b/i],
  ['"outage"', /\boutage\b/i],
  ['"took/brought ... down"', /\b(took|takes|taking|brought|bringing|knocked)\b[^.]{0,40}\bdown\b/i],
  ['history verb "broke"', /\bbroke\b/i],
  ['"previously"', /\bpreviously\b/i],
  ['"used to"', /\bused to\b/i],
  ['"no longer" / "not anymore"', /\bno longer\b|\bnot\b[^.]{0,20}\banymore\b/i],
  [
    '"initially / originally didn\'t / lacked"',
    /\b(initial(ly)?|original(ly)?|at first|early on)\b[^.]{0,40}\b(didn'?t|did not|does not|doesn'?t|lack(ed|s)?|had no|has no|was missing|wasn'?t|couldn'?t)\b/i,
  ],
  ['"was missing until" / "missing until"', /\bmissing until\b/i],
  ['"caught after the fact / in review"', /\bcaught\b[^.]{0,30}\b(after the fact|later|in review|post[- ]hoc|once)\b/i],
  ['"we tried X"', /\bwe tried\b/i],
  ['"an inconsistency"', /\ban inconsistenc(y|ies)\b/i],
  ['"regression"', /\bregression\b/i],
  ['"unlike before / the old ..."', /\bunlike\b[^.]{0,20}\b(before|the (old|previous|earlier|original))\b/i],
  ['"this now ..." (implies a change)', /\bthis now\b|\bnow (correctly|finally|properly)\b/i],
  ['bare YYYY-MM-DD date', /(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])/],
  [
    'issue / PR number reference',
    // #123 not adjacent to hex (so CSS colours like #1F9D55 / #121815 don't
    // trip it), or an explicit "issue 123" / "PR 123".
    /(?<![0-9A-Fa-f#])#\d{1,5}(?![0-9A-Fa-f-])|\b(issues?|PRs?|pull requests?)\s+#?\d{1,6}\b/i,
  ],
];

// In test files these phrasings are ordinary (a test literally named for the
// regression it locks, a docstring citing the issue it reproduces), so drop
// them there rather than crying wolf on every new test.
const TEST_SUPPRESSED = new Set([
  '"regression"',
  '"an inconsistency"',
  'issue / PR number reference',
]);

const lines = added.split('\n');
const hits = [];

let inPyDoc = false; // inside a """ / ''' block
let inTsBlock = false; // inside a /* ... */ block
let inMdFence = false; // inside a ``` / ~~~ fence

for (let i = 0; i < lines.length; i++) {
  const raw = lines[i];
  const trimmed = raw.trim();
  let prose = null;

  if (isMd) {
    if (/^(```|~~~)/.test(trimmed)) {
      inMdFence = !inMdFence;
      continue;
    }
    if (inMdFence) continue;
    prose = trimmed;
  } else if (isPy) {
    const tq = (raw.match(/"""|'''/g) || []).length;
    const wasInDoc = inPyDoc;
    if (tq % 2 === 1) inPyDoc = !inPyDoc;
    if (wasInDoc || inPyDoc || tq > 0) {
      prose = trimmed.replace(/"""|'''/g, '').replace(/^#+/, '');
    } else if (trimmed.startsWith('#') && !trimmed.startsWith('#!')) {
      prose = trimmed.replace(/^#+/, '');
    }
  } else {
    // .ts / .tsx
    const wasInBlock = inTsBlock;
    const opensBlock = raw.includes('/*');
    const closesBlock = raw.includes('*/');
    if (opensBlock && !closesBlock) inTsBlock = true;
    else if (inTsBlock && closesBlock) inTsBlock = false;

    if (wasInBlock || (opensBlock && !closesBlock)) {
      prose = trimmed.replace(/^[/*]+/, '').replace(/\*\/.*/, '');
    } else if (trimmed.startsWith('//')) {
      prose = trimmed.replace(/^\/+/, '');
    } else if (opensBlock && closesBlock) {
      prose = raw.replace(/.*?\/\*/, '').replace(/\*\/.*/, '');
    } else {
      const idx = raw.indexOf('//');
      if (idx > 0 && raw[idx - 1] !== ':') prose = raw.slice(idx + 2);
    }
  }

  if (!prose) continue;

  for (const [label, re] of MARKERS) {
    if (isTest && TEST_SUPPRESSED.has(label)) continue;
    if (re.test(prose)) {
      hits.push({ line: i + 1, label, text: trimmed.slice(0, 140) });
    }
  }
}

if (hits.length === 0) process.exit(0);

const seen = new Set();
const bullets = [];
for (const h of hits) {
  const key = h.label + '::' + h.text;
  if (seen.has(key)) continue;
  seen.add(key);
  bullets.push(`  • [${h.label}] ${h.text}`);
}

const message =
  `Possible incident-narration in ${base} (heuristic, non-blocking):\n` +
  bullets.join('\n') +
  `\n\nCLAUDE.md documentation policy: comments and docs describe current-state ` +
  `behavior only — past bugs, outages, "we tried X", "used to / initially ` +
  `lacked", and issue-number chains belong in git history and closed issues. ` +
  `Re-read the lines above; if any narrate how the code got this way rather ` +
  `than what it does now, rewrite them as present-tense mechanism (or drop them).`;

process.stdout.write(
  JSON.stringify({
    systemMessage: message,
    hookSpecificOutput: {
      hookEventName: 'PostToolUse',
      additionalContext: message,
    },
  })
);
process.exit(0);
