# Updates

Milestones and notable changes to Goodgorithm, newest first. Nothing to sign up for:
bookmark this page, subscribe to its [feed](/updates.atom), or watch the repo's
[Announcements](https://github.com/goodgorithm/goodgorithm/discussions/categories/announcements)
on GitHub.

Goodgorithm is in early development, so expect this list to be sparse for now and the app
itself to be rough around the edges.

## 2026-08-28 — Groundwork for native apps

Work started on Capacitor-wrapped iOS and Android builds of the same feed — one codebase,
no separate native app to maintain. They're not in the app stores yet; for now the
"Add to Home Screen" web app is the way to use Goodgorithm on a phone.

## 2026-08-27 — The feed loads faster

The page now paints a skeleton feed almost immediately instead of waiting for the
JavaScript bundle to download first, so there's something on screen sooner on a slow
connection.
