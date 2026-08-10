from uuid import uuid4

import bot_filter


class InMemoryBotFilterIndex:
    """Test double for bot_filter.BotFilterIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.velocity: dict[str, int] = {}
        self.cluster_authors: dict[str, set[str]] = {}

    def bump_velocity(self, author_id: str) -> int:
        self.velocity[author_id] = self.velocity.get(author_id, 0) + 1
        return self.velocity[author_id]

    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool:
        members = self.cluster_authors.setdefault(cluster_id, set())
        if author_id in members:
            return True
        members.add(author_id)
        return False


def test_url_density_counts_links_against_word_count():
    assert bot_filter.url_density("just a normal post with no links") == 0.0
    assert bot_filter.url_density("check https://a.com and https://b.com") == 2 / 4


def test_url_density_matches_bare_www_links_with_no_scheme():
    # Regression: a real promotional post's 4 Amazon links, written as
    # "www.amazon.com/dp/..." with no "http(s)://", scored zero url_density
    # and slipped through this filter (confirmed 2026-08-11).
    text = (
        "Book 4 out now\n"
        "www.amazon.com/dp/B0HBRCJBS1\n"
        "www.amazon.co.uk/dp/B0HBRCJBS1\n"
        "www.amazon.com.au/dp/B0HBRCJBS1\n"
        "www.amazon.ca/dp/B0HBRCJBS1"
    )
    # 8 whitespace-split words total (4 prose + 4 links), 4 of which match.
    assert bot_filter.url_density(text) == 4 / 8


def test_hashtag_density():
    assert bot_filter.hashtag_density("no hashtags here") == 0.0
    assert bot_filter.hashtag_density("#deal #sale #now buy") == 3 / 4


def test_caps_ratio_ignores_short_words():
    # "US" and "AI" are short acronyms, shouldn't count against the ratio
    assert bot_filter.caps_ratio("the US AI report is out") == 0.0
    assert bot_filter.caps_ratio("BUY NOW CLICK HERE today") == 4 / 5


def test_lexical_score_flags_link_stuffing():
    spammy = "https://x.co/1 https://x.co/2 https://x.co/3 free money"
    clean = "had a lovely walk in the park this morning"
    assert bot_filter.lexical_score(spammy) > 0.8
    assert bot_filter.lexical_score(clean) == 0.0


def test_score_bot_normal_post_is_not_flagged():
    index = InMemoryBotFilterIndex()
    result = bot_filter.score_bot(
        author_id="alice",
        text="had a lovely walk in the park this morning",
        cluster_id=uuid4(),
        index=index,
    )
    assert result.is_bot is False
    assert result.bot_score < bot_filter.BOT_SCORE_THRESHOLD


def test_score_bot_rapid_fire_posting_raises_velocity_component():
    # velocity alone, even maxed out, is deliberately not enough to flag
    # is_bot on its own (weight 0.4 < threshold 0.5) — a genuinely active
    # human during breaking news shouldn't get flagged from this signal
    # alone. It should still visibly raise the score, though.
    index = InMemoryBotFilterIndex()
    author = "busy_human"
    text = "totally normal post text here"

    first = bot_filter.score_bot(author, text, uuid4(), index)
    for _ in range(20):
        last = bot_filter.score_bot(author, text, uuid4(), index)

    assert last.velocity_component > first.velocity_component
    assert last.velocity_component == 1.0
    assert last.is_bot is False


def test_score_bot_rapid_fire_plus_self_duplication_flags_as_bot():
    # the realistic spam pattern: same content, blasted repeatedly, into
    # the same dedup cluster — velocity + self-dup together should cross
    # the threshold even though velocity alone doesn't.
    index = InMemoryBotFilterIndex()
    author = "spammer"
    text = "buy cheap watches now, link in bio"
    cluster_id = uuid4()

    for _ in range(20):
        last = bot_filter.score_bot(author, text, cluster_id, index)

    assert last.self_dup_component == 1.0
    assert last.velocity_component == 1.0
    assert last.is_bot is True


def test_score_bot_self_duplicate_flagged_on_second_post_into_same_cluster():
    index = InMemoryBotFilterIndex()
    author = "repeater"
    cluster_id = uuid4()

    first = bot_filter.score_bot(author, "buy my product", cluster_id, index)
    second = bot_filter.score_bot(author, "buy my product", cluster_id, index)

    assert first.self_dup_component == 0.0
    assert second.self_dup_component == 1.0


def test_score_bot_different_authors_same_cluster_not_self_duplicate():
    index = InMemoryBotFilterIndex()
    cluster_id = uuid4()

    result_a = bot_filter.score_bot("alice", "breaking news update", cluster_id, index)
    result_b = bot_filter.score_bot("bob", "breaking news update", cluster_id, index)

    assert result_a.self_dup_component == 0.0
    assert result_b.self_dup_component == 0.0
