import logging
import os

from infra import db

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


def detect_clusters() -> list[db.ClusterCandidate]:
    return db.fetch_cluster_candidates(
        min_accounts=NETWORK_DETECTOR_MIN_CLUSTER_ACCOUNTS,
        max_creation_span_days=NETWORK_DETECTOR_MAX_ACCOUNT_CREATION_SPAN_DAYS,
        min_post_count=NETWORK_DETECTOR_MIN_CLUSTER_POST_COUNT,
    )


def record_clusters(candidates: list[db.ClusterCandidate]) -> int:
    db.upsert_flagged_clusters(candidates)
    if candidates:
        logger.info(
            "flagged %d candidate account cluster(s) for review: %s",
            len(candidates),
            ", ".join(f"{c.home_domain} ({c.account_count} accounts)" for c in candidates),
        )
    return len(candidates)
