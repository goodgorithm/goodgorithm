---
name: run-web
description: Build, run, and drive Goodgorithm's web/ PWA (React + Vite) in a headless browser. Use when asked to start web/, screenshot its UI, verify a frontend change, or interact with the running feed.
---

`web/` is a static PWA with no server component of its own - it's driven
by starting Vite's dev server plus a mock `/health`+`/v1/feed` backend, then
scripting a headless Chromium against it via this skill's `driver.mjs`
(`chromium-cli` isn't installed on this machine, so this REPL stands in
for it - same command vocabulary, piped the same way).

All paths below are relative to `web/`.

## Setup

One-time, inside this skill directory (isolated `node_modules` - does
not touch `web/`'s own dependencies):

```bash
cd .claude/skills/run-web && npm install
```

This installs Playwright. Chromium's browser binary is already present
on this machine (no `npx playwright install chromium` needed) - if
`driver.mjs` fails to launch with a "browser not found" error on a
different machine, run that install command once.

`web/`'s own deps still need the usual `npm install` at `web/` root if
not already done.

## Run (agent path)

`api/` needs a real Postgres (`DATABASE_URL`) to run, which isn't
available here - so for driving `web/` alone, point it at the bundled
mock instead of a real `api/` instance. The mock serves 105 posts (one
deliberately long, to exercise post auto-collapse) with working cursor
pagination, matching `web/src/api/types.ts`'s `FeedResponse`/`FeedPost`
shape.

```bash
# from web/
node e2e/mock-api.mjs 4100 > /tmp/mock-api.log 2>&1 &
disown

VITE_API_BASE_URL=http://localhost:4100 npm run dev > /tmp/vite-dev.log 2>&1 &
disown

for i in $(seq 1 30); do curl -sf http://localhost:5173 >/dev/null && echo ready && break; sleep 1; done
```

Then drive it by piping commands to `driver.mjs`:

```bash
node .claude/skills/run-web/driver.mjs --out /tmp/shots <<'EOF'
nav http://localhost:5173
wait-for text=Short uplifting post number 0.
screenshot 01-initial
console
quit
EOF
```

Screenshots land in the `--out` directory (`/tmp/shots/01-initial.png`
above). Logs → `/tmp/vite-dev.log`, `/tmp/mock-api.log`.

| command | what it does |
|---|---|
| `nav <url>` | navigate |
| `wait-for text=<text>` or `wait-for <selector>` | wait until present |
| `screenshot [name]` | screenshot to `--out`, defaults to `001.png`, `002.png`, ... |
| `click text=<text>` or `click <selector>` | click first match |
| `fill <selector> <value>` | fill an input |
| `press <key>` | keyboard press |
| `eval <js-expression>` | evaluate in-page, prints JSON result |
| `scroll-bottom` | scroll to bottom (triggers infinite-scroll fetch) |
| `reload` | reload the page |
| `emulate-color-scheme <light\|dark\|no-preference>` | force the OS-level color scheme (for testing `prefers-color-scheme` theming) |
| `console` | dump captured `console.error`/`pageerror` entries |
| `quit` | close the browser and exit |

Stop the background processes when done:

```bash
lsof -ti:5173 -sTCP:LISTEN | xargs -r kill
lsof -ti:4100 -sTCP:LISTEN | xargs -r kill
```

## Run (human path)

```bash
VITE_API_BASE_URL=http://localhost:4100 npm run dev   # → http://localhost:5173, Ctrl-C to stop
```

Needs a real or mock API at that URL (see above) - `client.ts` throws
immediately if `VITE_API_BASE_URL` is unset.

## Build

```bash
npm run build   # tsc -b && vite build - type-checks and produces dist/
```

## Test

```bash
npm test    # vitest run
npm run lint  # oxlint
```

---

## Gotchas

- **Bare `playwright` (this driver) isn't a `web/` devDependency, but
  `@playwright/test` (the real E2E suite, `web/e2e/*.spec.ts`) is.**
  Different use cases: this driver is for interactive, agent-led
  one-off debugging (this file), kept isolated in
  `.claude/skills/run-web/package.json` since it's not something a
  human contributor runs; `@playwright/test` is the documented,
  contributor-facing pre-push/pre-merge multi-browser check (see
  CONTRIBUTING.md), so it lives in `web/package.json` like any other
  real dev dependency. Don't `npm install playwright` at `web/` root
  for *this* driver - `cd` into the skill dir first.
- **`api/` can't run here without a real Postgres.** Don't try to spin
  up `api/` for frontend verification - use `e2e/mock-api.mjs` (shared
  with the Playwright E2E suite), which matches the response shape
  closely enough for the feed, infinite scroll, auto-collapse, and
  anti-repeat/cursor-persistence features to all render and behave
  correctly against it.
- **No `timeout` binary on this machine (macOS).** The dev-server
  readiness check above uses a polling `for` loop instead of
  `timeout 30 bash -c '...'` - if adapting this on Linux, either works.
- **Bare `npx playwright ...` module resolution.** `npx --package=playwright
  node script.mjs` does *not* put `playwright` on Node's ESM resolution
  path (`NODE_PATH` doesn't affect `import` resolution either) - this
  is exactly why the driver gets its own local `node_modules` via
  `npm install` in Setup, rather than trying to resolve through `npx`'s
  cache at run time.

## Troubleshooting

- **`VITE_API_BASE_URL is required` thrown on page load**: the env var
  wasn't set before `npm run dev` started. Kill the dev server
  (`lsof -ti:5173 -sTCP:LISTEN | xargs -r kill`) and relaunch with it set.
- **`driver.mjs` hangs on `wait-for`**: usually means the dev server or
  mock API isn't actually up yet - check `/tmp/vite-dev.log` and
  `/tmp/mock-api.log`, and confirm both `curl -sf http://localhost:5173`
  and `curl -sf http://localhost:4100/health` succeed first.
- **`EADDRINUSE` on relaunch**: a previous run's dev server or mock API
  is still listening. `lsof -ti:5173 -sTCP:LISTEN | xargs -r kill` and
  the same for `4100` before starting again.
