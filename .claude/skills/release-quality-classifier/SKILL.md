---
name: release-quality-classifier
description: Train, evaluate, and publish a new version of Goodgorithm's quality classifier (the #238 epic's "would a human call this good" signal — positivity and substance together, not substance alone). Training runs in a plain Python environment (no GPU needed — TF-IDF + logistic regression trains on CPU in minutes); this skill covers producing a fresh training export, the mandatory every-run threshold re-assessment, what to check in the eval output before trusting a new model, and promoting or rolling back the live version in R2. Use when asked to train a new quality-classifier model, retrain/update it, or publish/promote/rollback a version.
---

# Releasing a new quality classifier version

`processing/src/pipeline_stages/quality_model.py` loads this classifier from Cloudflare R2
(`quality-classifier/latest.json`, once per process). This skill covers
training a new version, deciding whether it's good enough, and making it live — without ever
silently pushing an unreviewed model to production.

Read `CLAUDE.md` in the repo root first if you haven't — this skill assumes the "no LLM in
the algorithm" constraint and the R2 versioning scheme it describes.

## The release model

Every training run publishes its artifacts to `quality-classifier/<version>/` in the
`goodgorithm-models` R2 bucket (`model.onnx`, `config.json` — no separate vocab file, since the TF-IDF vocabulary is baked into the exported ONNX graph) — that
always happens, and it's cheap and reversible. Separately, `quality-classifier/latest.json`
points at whichever version `processing/` actually loads at startup. **Publishing a version
and promoting it to latest are two different, deliberately separate actions**, same as every
other model type.

`goodgorithm-models` is a **private** R2 bucket — `training/r2_release.py --model quality
publish <version>` mirrors the artifacts to a public GitHub Release
(`quality-classifier-<version>`), same "open-source model weights" reasoning as every other
model type.

## Steps

1. **Produce a fresh training export.** Follow `doc/LABEL_EXPORT.md` to export reviewed posts
   from the `labeling` schema as a JSON file. This classifier trains directly on Goodgorithm's
   own labelled set, not a public dataset — a fresh export is a real, required input every run, not a one-time fixed dataset.

2. **Decide the text-normalization state you're training against.**
   `processing/src/util/text_normalize.py` defines the normalization the classifier's TF-IDF
   vectorizer is trained against, and the notebook fetches it from a *pinned commit*, not
   `main` — so a later edit can never silently invalidate an already-published model. If you
   haven't changed `text_normalize.py`, the existing pin is fine. If you have, get the new
   commit's SHA (`git rev-parse HEAD` on `main` after merging) before continuing.

3. **Open `training/quality_classifier.ipynb`.** **This doesn't need a GPU or Colab/Kaggle** — TF-IDF + logistic regression trains on CPU in a
   couple of minutes, so it can run anywhere Python + the notebook's `pip install` cell can
   run. Update:
   - The upload cell with your fresh export from step 1.
   - `TEXT_NORMALIZE_COMMIT` — the SHA from step 2, if it changed.
   - `VERSION` (near the R2 upload cell) — bump it (e.g. `v1` → `v2`). Versions are immutable
     once published.

4. **Run cells top to bottom through the honest-evaluation and full-fit sections.** Provide R2
   credentials the same way as the other models (Colab/Kaggle Secrets if running there, or
   local `.env`/shell export otherwise — same `R2_MODELS_ACCOUNT_ID`/`R2_MODELS_ACCESS_KEY_ID`/
   `R2_MODELS_SECRET_ACCESS_KEY`/`R2_MODELS_BUCKET_NAME` vars). Check the out-of-fold AUC
   (good vs. `shouldnt-be-shown`) printed — the first run's reference is 0.7734; a large
   deviation on a later run means something about the export or normalization has changed in
   a way worth understanding before continuing, not just an expected drift from more data.

5. **The threshold re-assessment section is mandatory and blocking.** This classifier's
   deployment threshold is re-derived from scratch **every single training run**, using the same
   methodology originally established for #238 (see that issue's closing comments for the
   full derivation): a fine-grained sweep, a good-retention-floor-constrained candidate table,
   and a bootstrap stability check. The notebook hard-blocks every cell after this section (config
   packaging, ONNX export, upload) behind a `THRESHOLD = None` assertion — **you must read the
   printed tables and set it explicitly before the notebook will let you continue.**
   - Compare against the currently-published version's threshold (`training/r2_release.py
     --model quality current`, then that version's `config.json` from R2) — a materially
     different number than what's currently live is worth a second look or a discussion
     before publishing, not an automatic override. The whole reason this is re-assessed every
     run rather than left at 0.39 forever is to track real drift in the data over time — but
     "the number moved" and "the number moved for a good, understood reason" are different
     things, and only the second one should change what ships.
   - **Do not bypass this by pre-filling `THRESHOLD` with a hardcoded value without actually
     reading the tables first.** That defeats the entire point of re-running the assessment
     every time — it would silently reintroduce the "frozen number nobody re-checks" problem
     this process exists to avoid.

6. **Before considering promotion, also check:**
   - **The spot-check examples.** A model acing the metrics above but failing obvious
     spot-checks is a red flag worth catching before publishing.
   - **The ONNX export cell's own assertions** — output-name order, output width (2 classes),
     and numeric parity vs. `clf.predict_proba()`. Don't skip past a failure here by
     re-running with looser tolerances without understanding why parity failed — this
     classifier's vectorizer config (`stop_words="english"` + `token_pattern=r"\b\w+\b"`) is a
     combination not validated by any prior model in this repo, so a first-time parity failure
     here is plausible and needs to actually be resolved, not tolerance-widened away.

   There's no hard pass/fail bar — judge this run's numbers against the previous live
   version's, not an absolute target. There's no fallback model for this signal: with no
   version loaded, `quality_score` is `NULL` on every post (fail-open — the quality exclude
   never fires and `compute_base_score` treats the score as `0.0`).

7. **The notebook always uploads the versioned artifacts** (`quality-classifier/<version>/
   model.onnx`, `config.json`) regardless of the promotion decision — safe and reversible on
   its own. If the notebook was run somewhere other than an interactive session with R2 access,
   upload manually instead: `cd training && uv run python r2_release.py --model quality
   upload <version> --path <local-dir>` — `<local-dir>` needs exactly `model.onnx` and
   `config.json` under those plain names.

8. **Promote to live only if step 6 looks good:**
   - `cd training && uv run python r2_release.py --model quality publish <version>` (needs
     the `R2_MODELS_*` env vars and an authenticated `gh` CLI with access to
     `goodgorithm/goodgorithm`).
   - This flips `quality-classifier/latest.json` **and** creates a public GitHub Release
     (`quality-classifier-<version>`).

9. **Verify:** `uv run python r2_release.py --model quality current` should print the new
   version, and `gh release view quality-classifier-<version> --repo goodgorithm/goodgorithm`
   should show the public release. `processing/` picks up the model the next time a process
   starts (resolved once per process, on first use) — a running deployment needs a restart to
   pick up a newly-promoted version.

   **The real verification** is `processing/`'s `GET /health` (`models.quality.version` should
   show the new version) plus the `processed_posts` columns themselves — run against staging
   after a soak period, then again against production after promoting there:
   ```sql
   SELECT quality_method, COUNT(*), AVG(quality_score)
   FROM processed_posts WHERE processed_at > NOW() - INTERVAL '1 hour'
   GROUP BY quality_method;
   ```
   Non-pending rows should be overwhelmingly `tfidf_lr_v1`. A high `NULL` share outside
   `context_status = 'pending'` rows usually means the model failed to load (check logs).

10. **The GitHub Release created in step 8 is the durable record of this promotion** — it
    captures the version, dataset composition, the full threshold-selection table, and the
    threshold that was chosen, via `config.json`'s contents.

## Rolling back

Identical mechanism to every other model: `uv run python r2_release.py --model quality list`,
then `uv run python r2_release.py --model quality publish <previous-version>` — no
retraining needed.

## Guardrails this skill exists to protect

- Don't hand-write a `boto3` upload/promote script inline — use `training/r2_release.py
  --model quality ...`, generalized rather than forked (`CLAUDE.md`: "extend this shape to a
  new integration point before inventing a different one").
- Don't skip the text-normalization commit pin, same reasoning as every other model.
- **Don't skip or shortcut the threshold re-assessment section** — pre-filling `THRESHOLD`
  without reading the sweep/floor/bootstrap tables defeats the reason this process exists.
  If the tables suggest a materially different number than what's live, that's worth a
  deliberate discussion, not a quiet change.
- Don't skip past an ONNX export assertion failure — this classifier's specific vectorizer
  config hasn't been battle-tested by a prior model in this repo.
- Don't reach for ad hoc scripts as a substitute for this notebook — #238's research
  prototyped this signal in throwaway scripts that found and validated it, not a training
  pipeline; this notebook is the real thing.
- This process trains a classical TF-IDF + logistic regression model on Goodgorithm's own
  labelled data — it doesn't touch the "no LLM in the algorithm" boundary. If a future request
  asks to replace this model with an LLM-based classifier, that's a project-level decision
  (see `CLAUDE.md`), not something to do inside this skill.
