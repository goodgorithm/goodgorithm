import logging
import os

from infra import db
from util import bluesky_funnel

logger = logging.getLogger("processing")

# Surfaces candidate coordinated bot networks for a moderator to review --
# never auto-blocks anything, same "human-decided" precedent as the
# blocked_authors moderation blocklist. The signal is same-domain Mastodon
# accounts whose real account-creation dates cluster tightly, not raw
# same-domain account count -- see the wiki's Processing Infrastructure page
# for why the obvious-looking "many accounts, one domain" signal was tested
# and rejected. Starting points, not empirically tuned yet -- treat as
# unvalidated, same as every other threshold in this codebase.
NETWORK_DETECTOR_MIN_CLUSTER_ACCOUNTS = int(os.environ.get("NETWORK_DETECTOR_MIN_CLUSTER_ACCOUNTS", "5"))
NETWORK_DETECTOR_MAX_ACCOUNT_CREATION_SPAN_DAYS = int(
    os.environ.get("NETWORK_DETECTOR_MAX_ACCOUNT_CREATION_SPAN_DAYS", "14")
)
NETWORK_DETECTOR_MIN_CLUSTER_POST_COUNT = int(os.environ.get("NETWORK_DETECTOR_MIN_CLUSTER_POST_COUNT", "50"))

# --- Bluesky funnel-network flag -------------------------------------------
# Bluesky has no home instance to cluster on, so the unit is "every DID that
# posted the coordinated funnel shape (a funnel call-to-action phrase plus an
# adult/funnel hashtag bag -- util/bluesky_funnel.py's vocabulary) in the
# window." Deliberately a LOOSER adult-hashtag threshold than
# content_filter.FUNNEL_MIN_ADULT_HASHTAGS: by the time this hourly aggregate
# runs, run_cycle has already deleted the flagrant posts (the ones over the
# per-post threshold) from raw_posts, so matching that exact shape here would
# find almost nothing -- the looser bar re-identifies the same accounts
# through their weaker, still-present posts (a CTA phrase plus 2-4 adult
# tags) that the per-post arm leaves in. Never auto-blocks; writes one
# synthetic-key row to flagged_author_clusters for a moderator to review and
# bulk-block. Starting points, not empirically tuned -- same status as the
# Mastodon thresholds above.
NETWORK_DETECTOR_BLUESKY_FUNNEL_WINDOW_HOURS = int(
    os.environ.get("NETWORK_DETECTOR_BLUESKY_FUNNEL_WINDOW_HOURS", "24")
)
NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_ADULT_HASHTAGS = int(
    os.environ.get("NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_ADULT_HASHTAGS", "2")
)
NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_DIDS = int(
    os.environ.get("NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_DIDS", "5")
)

# One flagged_author_clusters row for the whole Bluesky funnel signal --
# that table keys on home_domain (TEXT NOT NULL UNIQUE) and there is exactly
# one known Bluesky network; a value that can never collide with a real
# Mastodon home domain. A second distinct network would take a second
# synthetic key. NOTE: setting dismissed_at on this one row silences ALL
# Bluesky funnel detection (unlike the Mastodon path's one row per domain)
# -- see doc/MODERATION.md; the intended action is blocking the DIDs.
_BLUESKY_FUNNEL_CLUSTER_KEY = "bluesky:funnel-network"


def detect_clusters() -> list[db.ClusterCandidate]:
    return db.fetch_cluster_candidates(
        min_accounts=NETWORK_DETECTOR_MIN_CLUSTER_ACCOUNTS,
        max_creation_span_days=NETWORK_DETECTOR_MAX_ACCOUNT_CREATION_SPAN_DAYS,
        min_post_count=NETWORK_DETECTOR_MIN_CLUSTER_POST_COUNT,
    )


def detect_bluesky_funnel_cluster() -> list[db.ClusterCandidate]:
    cluster = db.fetch_bluesky_funnel_cluster(
        window_hours=NETWORK_DETECTOR_BLUESKY_FUNNEL_WINDOW_HOURS,
        min_adult_hashtags=NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_ADULT_HASHTAGS,
        min_dids=NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_DIDS,
        cta_pattern=bluesky_funnel.FUNNEL_CTA_PATTERN,
        adult_vocab=sorted(bluesky_funnel.ADULT_FUNNEL_HASHTAGS),
    )
    if cluster is None:
        return []
    logger.info(
        "bluesky funnel cluster: %d DID(s), %d post(s); sample captions: %s",
        len(cluster.dids),
        cluster.post_count,
        " | ".join(cluster.sample_captions),
    )
    return [
        db.ClusterCandidate(
            home_domain=_BLUESKY_FUNNEL_CLUSTER_KEY,
            author_ids=sorted(cluster.dids),
            account_count=len(cluster.dids),
            post_count=cluster.post_count,
            # Bluesky has no account-creation timestamp; these NOT NULL
            # columns carry the matched posts' created_at range instead.
            earliest_account_created_at=cluster.earliest_created_at,
            latest_account_created_at=cluster.latest_created_at,
        )
    ]


def record_clusters(candidates: list[db.ClusterCandidate]) -> int:
    db.upsert_flagged_clusters(candidates)
    if candidates:
        logger.info(
            "flagged %d candidate account cluster(s) for review: %s",
            len(candidates),
            ", ".join(f"{c.home_domain} ({c.account_count} accounts)" for c in candidates),
        )
    return len(candidates)
