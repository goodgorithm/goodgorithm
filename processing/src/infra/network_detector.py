import logging

from infra import db

logger = logging.getLogger("processing")

# Issue #44: surfaces candidate coordinated bot networks for a moderator to
# review -- never auto-blocks anything, same "human-decided" precedent as
# the blocked_authors moderation blocklist (issue #7). Prompted by the
# pubeurope.com takedown (96 accounts), which was found entirely by hand:
# a moderator noticed one post, then had to manually investigate to find
# the other 95.
#
# The obvious-looking signal ("many accounts share a Mastodon home
# domain") was tested against real production data before building this
# and rejected -- mastodon.social alone has 8,852 distinct posting
# accounts, bsky.brid.gy (Bridgy Fed's bridge domain, used by thousands of
# individually-bridged real Bluesky users) has 3,768. Both would trip a
# bare "N+ accounts, one domain" rule. The actual distinguishing signal:
# many same-domain accounts whose real Mastodon account-creation dates
# cluster tightly (a sudden batch of new accounts), not "when we first
# saw a post from them" (retention-windowed, looks clustered for every
# account regardless of true age).
#
# Starting points, not empirically tuned -- the pubeurope.com rows were
# already purged as part of the manual takedown, so there was no way to
# calibrate directly against that case. Expect to adjust after this runs
# against real data for a while, same as every other threshold in this
# codebase (bot_filter.py's weights, language_filter.py's confidence
# threshold, etc.).
MIN_CLUSTER_ACCOUNTS = 5
MAX_ACCOUNT_CREATION_SPAN_DAYS = 14
MIN_CLUSTER_POST_COUNT = 50


def detect_clusters() -> list[db.ClusterCandidate]:
    return db.fetch_cluster_candidates(
        min_accounts=MIN_CLUSTER_ACCOUNTS,
        max_creation_span_days=MAX_ACCOUNT_CREATION_SPAN_DAYS,
        min_post_count=MIN_CLUSTER_POST_COUNT,
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
