---
name: release-category-classifier
description: Train, evaluate, and publish a new version of Goodgorithm's category classifier. Training runs in a plain Python environment (no GPU needed - TF-IDF + logistic regression trains on CPU in minutes); this skill covers the label-order-parity check, what to check in the eval output before trusting a new model (especially per-label support counts and the confidence threshold), and promoting or rolling back the live version in R2. Use when asked to train a new category model, retrain/update the category classifier, or publish/promote/rollback a category model version.
---

# Releasing a new category classifier version

`processing/src/category_model.py` categorizes posts with a TF-IDF + one-vs-rest logistic regression classifier loaded from Cloudflare R2, falling back to `taxonomy.py`'s keyword matcher if no model is available. This skill covers the full loop: training a new version, deciding whether it's good enough, and making it live — without ever silently pushing an unreviewed model to production.

Read `CLAUDE.md` in the repo root first if you haven't — this skill assumes the "no LLM in the algorithm" constraint and the R2 versioning scheme it describes. Also read `.claude/skills/release-sentiment-model/SKILL.md` — this skill mirrors its structure closely; only the differences are called out in detail here.

## The release model

Every training run publishes its artifacts to `category-classifier/<version>/` in the `goodgorithm-models` R2 bucket (`model.onnx`, `config.json` — only two, not three; there's no separate vocab file, the TF-IDF vocabulary is baked into the exported ONNX graph) — that always happens, and it's cheap and reversible since nothing reads an unreferenced version. Separately, `category-classifier/latest.json` points at whichever version `processing/` actually loads at startup. **Publishing a version and promoting it to latest are two different, deliberately separate actions**, same as the sentiment model.

`goodgorithm-models` is a **private** R2 bucket — `training/r2_release.py --model category publish <version>` closes the same "open-source model weights" gap the sentiment model has, mirroring its three artifacts (well, two, for this model) to a public GitHub Release (`category-classifier-<version>`).

## Steps

1. **Decide the text-normalization state you're training against.** `processing/src/text_normalize.py` defines the normalization the classifier's TF-IDF vectorizer is trained against, and the notebook fetches it from a *pinned commit*, not `main` — so a later edit can never silently invalidate an already-published model. If you haven't changed `text_normalize.py`, the existing pin is fine. If you have, get the new commit's SHA (`git rev-parse HEAD` on `main` after merging) before continuing.

2. **Open `training/category_classifier.ipynb`.** Unlike the sentiment notebook, **this doesn't need a GPU or Colab/Kaggle** — TF-IDF + logistic regression trains on CPU in a couple of minutes, so it can run anywhere Python + the notebook's `pip install` cell can run, including this repo's own sandbox. Kept as a notebook anyway for parity with the sentiment model's audit trail. Update two things near the top:
   - `TEXT_NORMALIZE_COMMIT` — the SHA from step 1.
   - `VERSION` (near the R2 upload cell) — bump it (e.g. `v1` → `v2`). Versions are immutable once published.

3. **Run all cells top to bottom.** Provide R2 credentials the same way as the sentiment model (Colab/Kaggle Secrets if running there, or local `.env`/shell export otherwise — same `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME` vars).

4. **Before considering promotion, check the notebook's own output — this model has more to check than the sentiment CNN does, because of class imbalance:**
   - **Per-label positive counts** printed right after loading the training split. A category left with only a few hundred examples (some real ones run this low — `food_dining`/`travel_adventure` were ~100-130 in the first training run) is a genuine limitation, not a bug — but worth knowing before trusting that category's numbers.
   - **Per-label multi-label precision/recall/F1** from the `classification_report` cell. Expect real spread here — categories with more training data (e.g. `arts_culture`, `sports`) will score meaningfully better than thin ones. Don't average this away by only looking at macro/micro averages.
   - **The threshold sweep table**, and the confidence threshold chosen from it. This is the single most important judgment call in this notebook, and it's deliberately not automated (see the markdown cell right before the threshold is set): **issue #34's actual goal is more categorized volume, not maximum abstain-precision** — a threshold that trades away a lot of on-taxonomy accuracy for marginally better off-topic rejection works against the point of the whole project. Look for the knee of the curve (where accuracy is still close to its best value but off-taxonomy correctness has jumped substantially), not the threshold with the single highest combined score under some formula. Re-pick this by hand each run — the sweep numbers will vary run to run.
   - **The final confusion matrix**, including its `(none)` row/column — check it's not either (a) never abstaining (the pre-fix bug this notebook's evaluation section was specifically built to catch — see the "on the FULL test_2021 set" markdown cell for why) or (b) abstaining so often the model isn't adding value over the keyword-only fallback.
   - **The spot-check examples.** Same "obvious wrong answers are a red flag" reasoning as the sentiment model.
   - **The ONNX export cell's own assertions** — it already checks output-name and label-order-vs-`KEPT_LABELS` parity and will raise if either fails. Don't skip past a failure here by re-running with `--allow-errors` or similar; a label-order mismatch is a *silent* wrong-answer failure at inference time (the model loads fine, just confidently mislabels everything) — this cell existing and passing is the whole safety net for that.

   Same "no hard pass/fail bar, judge relatively" stance as the sentiment skill — but for a *first* version specifically, there's no prior version to judge against; judge against the keyword-only fallback's own real production numbers instead (issue #34's baseline: most categories under 10 posts, technology's ~126 as the best performer) — the bar to clear is "meaningfully more than that," not some absolute target.

5. **The notebook always uploads the versioned artifacts** (`category-classifier/<version>/model.onnx`, `config.json`) regardless of the decision in step 4 — safe and reversible on its own. If the notebook was run somewhere other than an interactive session with R2 access (e.g. artifacts produced elsewhere and handed off as local files), upload them manually instead: `cd training && uv run python r2_release.py --model category upload <version> --path <local-dir>` — `<local-dir>` needs exactly `model.onnx` and `config.json` under those plain names.

6. **Promote to live only if step 4 looks good:**
   - `cd training && uv run python r2_release.py --model category publish <version>` (needs the R2 env vars and an authenticated `gh` CLI with access to `goodgorithm/goodgorithm`, same as the sentiment model).
   - This flips `category-classifier/latest.json` **and** creates a public GitHub Release (`category-classifier-<version>`).

7. **Verify:** `uv run python r2_release.py --model category current` should print the new version, and `gh release view category-classifier-<version> --repo goodgorithm/goodgorithm` should show the public release. `processing/` picks up the model the next time a process starts (resolved once per process, on first categorization) — a running deployment needs a restart to pick up a newly-promoted version.

   **The real verification, though, is the same diagnostic query issue #34 used to find the problem in the first place** — run it against staging after a soak period, then again against production after promoting there:
   ```sql
   SELECT category, COUNT(*) FILTER (WHERE rank_score IS NOT NULL) AS eligible_and_ranked, COUNT(*) AS total
   FROM processed_posts GROUP BY category ORDER BY eligible_and_ranked DESC;
   ```
   Also check the `category_method` column's distribution — it should be overwhelmingly `tfidf_lr_v1`, not `keyword_v1`, once a version is live and processes have restarted. A high `keyword_v1` share post-promotion usually means the model failed to load (check logs), not that it's intentionally falling back.

8. **Record the release.** Add a line to the Decisions Log in Notion, same as the sentiment model — version, commit trained against, key eval numbers (including the per-label support counts and chosen threshold — those matter more for this model than a single aggregate score does).

## Rolling back

Identical to the sentiment model: `uv run python r2_release.py --model category list`, then `uv run python r2_release.py --model category publish <previous-version>`. If no version has ever been published, `category_model.py` fails open into keyword-only mode automatically — the genuine zero-risk floor, today's exact pre-classifier behavior.

## Guardrails this skill exists to protect

- Don't hand-write a `boto3` upload/promote script inline — use `training/r2_release.py --model category ...`, generalized from the sentiment model's release script rather than forked (`CLAUDE.md`: "extend this shape to a new integration point before inventing a different one").
- Don't skip the text-normalization commit pin, same reasoning as the sentiment model's tokenizer pin.
- Don't mechanically pick the threshold sweep's highest "combined score" without checking it actually favors on-taxonomy accuracy — the sweep is principled, a purely automated pick from it isn't (see step 4).
- Don't promote a version without checking the per-label support counts specifically, not just an aggregate score — this model's class imbalance is real and a macro-F1 alone hides it.
- Don't skip past an ONNX export assertion failure — it exists specifically to catch a silent label-order mismatch before it ever reaches production.
- This process trains a classical TF-IDF + logistic regression model on a public dataset — it doesn't touch the "no LLM in the algorithm" boundary. If a future request asks to replace this model with an LLM-based classifier, that's a project-level decision (see `CLAUDE.md`), not something to do inside this skill.
