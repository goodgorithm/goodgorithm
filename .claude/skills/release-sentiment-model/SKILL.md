---
name: release-sentiment-model
description: Train, evaluate, and publish a new version of Goodgorithm's sentiment CNN. Training runs in Google Colab/Kaggle (needs a GPU); this skill covers pinning the tokenizer commit, what to check in the eval output before trusting a new model, and promoting or rolling back the live version in R2. Use when asked to train a new sentiment model, retrain/update the sentiment CNN, or publish/promote/rollback a model version.
---

# Releasing a new sentiment CNN version

`processing/src/pipeline_stages/sentiment.py` scores posts with a small CNN loaded from Cloudflare R2, falling back to VADER if no model is available. This skill covers the full loop: training a new version, deciding whether it's good enough, and making it live — without ever silently pushing an unreviewed model to production.

Read `CLAUDE.md` in the repo root first if you haven't — this skill assumes the "no LLM in the algorithm" constraint and the R2 versioning scheme it describes.

## The release model

Every training run publishes its artifacts to `sentiment-cnn/<version>/` in the `goodgorithm-models` R2 bucket (`model.onnx`, `vocab.json`, `config.json`) — that always happens, and it's cheap and reversible since nothing reads an unreferenced version. Separately, `sentiment-cnn/latest.json` points at whichever version `processing/` actually loads at startup. **Publishing a version and promoting it to latest are two different, deliberately separate actions.** Never conflate them — a training run finishing successfully is not the same thing as it being safe to go live.

`goodgorithm-models` itself is a **private** R2 bucket (no public URL, confirmed 2026-08-12) — so on its own, uploading there does not fulfill the "we open-source model weights" commitment (the Mission/Algorithm pages on the GitHub Wiki). `training/r2_release.py`'s `publish` step closes that gap: promoting a version to live also mirrors its three artifacts to a public GitHub Release (`sentiment-cnn-<version>`, via the `gh` CLI). This only happens through `r2_release.py` — see step 6 below.

`r2_release.py` is generalized across model types (issue #34 added a `category` type alongside `sentiment`) via a required `--model` flag — every command below needs `--model sentiment` explicitly now, not just `current`/`list`/`publish` on their own.

## Steps

1. **Decide the tokenizer/vocab state you're training against.** `processing/src/sentiment_model.py` defines tokenization, and the notebook fetches it from a *pinned commit*, not `main` — so a later edit to that file can never silently invalidate an already-published model. If you haven't changed `sentiment_model.py`, the existing pin is fine. If you have, get the new commit's SHA (`git rev-parse HEAD` on `main` after merging) before continuing.

2. **Open `training/sentiment_cnn.ipynb` in Colab or Kaggle** (needs a GPU; this repo's sandbox/CI environments don't have one and this notebook should never be run there). Update two things near the top:
   - `SENTIMENT_MODEL_COMMIT` — the SHA from step 1.
   - `VERSION` (near the R2 upload cell) — bump it (e.g. `v1` → `v2`). Versions are immutable once published; reusing a version string to publish different weights defeats the point of versioning.

3. **Run all cells top to bottom.** Provide R2 credentials via Colab Secrets or Kaggle Secrets (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` — same values as `processing/`'s Railway env vars, see `.env.example`). The manual-paste fallback cell exists but secrets are strongly preferred — never commit real credentials into the notebook's saved output.

4. **Before considering promotion, check the notebook's own output:**
   - Macro-F1 on the held-out test split from the combined training pool.
   - Macro-F1 and the confusion matrix on TweetEval's *own* reserved test split — this is the more meaningful number since it's an independent, human-labeled, domain-matched benchmark that was never trained on.
   - The spot-check examples near the end (hand-written short posts with obvious expected sentiment). A model that aces the metrics above but gets these obviously wrong is a red flag worth investigating before publishing, not after.
   - GloVe coverage percentage from the embeddings cell — a sharp drop from prior runs suggests something upstream (tokenization, vocab building) changed unexpectedly.

   There's no hard pass/fail bar defined here on purpose — judge against the *previous* live version's numbers (check `training/r2_release.py --model sentiment current`, then that version's `config.json` in R2 for its recorded `best_val_macro_f1`), not an absolute target.

5. **The notebook always uploads the versioned artifacts** (`sentiment-cnn/<version>/model.onnx`, `vocab.json`, `config.json`) regardless of the decision in step 4 — that part is safe and reversible on its own. If the notebook was run somewhere other than an interactive session with R2 access (e.g. artifacts produced elsewhere and handed off as local files), upload them manually instead: `cd training && uv run python r2_release.py --model sentiment upload <version> --path <local-dir>` — `<local-dir>` needs exactly `model.onnx`, `vocab.json`, and `config.json` under those plain names.

6. **Promote to live only if step 4 looks good, via `r2_release.py`** — the only path that also makes the version public:
   - `cd training && uv run python r2_release.py --model sentiment publish <version>` (needs the R2 env vars, e.g. from a local `.env` or exported in your shell, *and* an authenticated `gh` CLI with access to `goodgorithm/goodgorithm`).
   - This flips `sentiment-cnn/latest.json` **and** creates a public GitHub Release (`sentiment-cnn-<version>`) mirroring the three artifacts from R2, since `goodgorithm-models` itself is a private bucket — see "The release model" above.
   - The notebook's `PUBLISH_AS_LATEST = True` cell still exists and flips `latest.json`, but Colab has no `gh`/repo access, so it **cannot** create the public release. If you use that cell, you still need to run `r2_release.py --model sentiment publish <version>` afterward (it's idempotent on the `latest.json` flip and will just create the missing release). Prefer `r2_release.py` as the single step going forward.

7. **Verify:** `uv run python r2_release.py --model sentiment current` should print the new version, and `gh release view sentiment-cnn-<version> --repo goodgorithm/goodgorithm` should show the public release. `processing/` picks the model up the next time a process starts — it resolves the live version once per process, on the first sentiment score, not continuously — so a running deployment needs a restart (a normal Railway redeploy) to pick up a newly-promoted version.

8. **Record the release.** Add a line to the Decisions Log in Notion (internal workspace) with the version, the commit it was trained against, and the key eval numbers from step 4 — this is part of the project's transparency commitment (publishing training data and model weights is only meaningful if there's also a record of *when* and *why* a version went live).

## Rolling back

If a live version turns out to be worse in production than its eval numbers suggested: `uv run python r2_release.py --model sentiment list` to see what's available, then `uv run python r2_release.py --model sentiment publish <previous-version>`. No need to retrain — this just repoints `latest.json`. Record the rollback in the Decisions Log too, with the reason.

## Guardrails this skill exists to protect

- Don't hand-write a `boto3` upload/promote script inline when asked to do this — use `training/r2_release.py`, which already matches `processing/src/infra/model_store.py`'s exact registry layout (`current`/`list`/`publish` check the same paths `sentiment.py` reads at inference time).
- Don't skip the tokenizer commit pin — training against unpinned `main` risks a silent train/inference mismatch that's very hard to debug after the fact (the model would still load and run, just score worse than its eval numbers imply).
- Don't promote a version without checking eval output first, even under time pressure — that's the entire reason publish and promote are separate steps.
- Don't promote via the notebook's `PUBLISH_AS_LATEST` cell alone and call it done — it flips `latest.json` but can't create the public GitHub Release, so the version would be live in production without actually being open-sourced. Always follow up with (or just use) `r2_release.py publish`.
- This process trains a small CNN on public datasets — it doesn't touch the "no LLM in the algorithm" boundary. If a future request asks to replace this model with an LLM-based scorer, that's a project-level decision (see `CLAUDE.md`), not something to do inside this skill.
