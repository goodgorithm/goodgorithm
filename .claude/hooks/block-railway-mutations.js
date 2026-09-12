#!/usr/bin/env node
'use strict';

/*
 * PreToolUse hard-block for Railway MCP tools: every call outside the fixed
 * read-only allowlist below is denied unconditionally. Claude does not
 * mutate live Railway infrastructure through these tools -- a human runs
 * those actions directly (dashboard or `railway` CLI). This is a hard
 * policy boundary, not left to the model's judgment: a hook has no
 * visibility into conversation intent, only the tool call itself, so an
 * unconditional block is the only mechanism that can't be reasoned around.
 *
 * To let a specific write through, add its action name to READ_ONLY below.
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

const toolName = String(payload.tool_name || '');
const PREFIX = 'mcp__claude_ai_Railway__';
if (!toolName.startsWith(PREFIX)) process.exit(0);

const action = toolName.slice(PREFIX.length);

// Read-only Railway MCP actions -- safe to run without a human in the loop.
// Everything else (create-/delete-/update-/set-/connect-/generate-/
// redeploy/restart-service/accept-deploy/railway-agent) is blocked below.
const READ_ONLY = new Set([
  'list-projects', 'list-services', 'list-deployments', 'list-variables',
  'list-domains', 'list-tcp-proxies', 'list-feature-flags', 'list-workspaces',
  'get-status', 'get-service-config', 'get-service-metrics',
  'get-deployment-diagnosis', 'get-feature-flag', 'get-logs',
  'environment-status', 'domain-status', 'whoami',
  'search-docs', 'fetch-docs',
  'http-error-rate', 'http-requests', 'http-response-time',
]);

if (READ_ONLY.has(action)) process.exit(0);

process.stdout.write(JSON.stringify({
  hookSpecificOutput: {
    hookEventName: 'PreToolUse',
    permissionDecision: 'deny',
    permissionDecisionReason:
      'Railway write action "' + action + '" is blocked by policy. Claude never ' +
      'mutates live Railway infrastructure directly -- tell the user the exact ' +
      'change needed and have them run it (dashboard or `railway` CLI).',
  },
}));
process.exit(0);
