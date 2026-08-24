from uuid import uuid4

from pipeline_stages import bot_filter


class InMemoryBotFilterIndex:
    """Test double for bot_filter.BotFilterIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.velocity: dict[str, int] = {}
        self.cluster_authors: dict[str, set[str]] = {}
        self.template_repeats: dict[str, int] = {}

    def bump_velocity(self, author_id: str) -> int:
        self.velocity[author_id] = self.velocity.get(author_id, 0) + 1
        return self.velocity[author_id]

    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool:
        members = self.cluster_authors.setdefault(cluster_id, set())
        if author_id in members:
            return True
        members.add(author_id)
        return False

    def bump_template_repeat(self, author_id: str, skeleton: str) -> int:
        key = f"{author_id}:{skeleton}"
        self.template_repeats[key] = self.template_repeats.get(key, 0) + 1
        return self.template_repeats[key]


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


# --- canonical_account_id (issue #78) ---


def test_canonical_account_id_qualifies_a_bare_acct_with_the_polled_instance():
    # The polled instance IS this account's home instance (Mastodon's own
    # `acct` field has no "@host" for a local account).
    assert bot_filter.canonical_account_id("mastodon", "fosstodon.org/localuser") == "localuser@fosstodon.org"


def test_canonical_account_id_leaves_an_already_qualified_acct_alone():
    # The polled instance sees this account as remote/federated -- acct is
    # already the globally-qualified form, so the polled instance itself
    # is irrelevant to this account's real identity.
    assert (
        bot_filter.canonical_account_id("mastodon", "hachyderm.io/zelenskyyua@zpravobot.news")
        == "zelenskyyua@zpravobot.news"
    )


def test_canonical_account_id_unifies_the_same_account_seen_via_different_polled_instances():
    # The actual regression: one real account, visible on several of our
    # polled instances' public timelines (crossposting, or just
    # federation), used to fragment into a distinct author_id per instance.
    variants = [
        "fosstodon.org/zelenskyyua@zpravobot.news",
        "hachyderm.io/zelenskyyua@zpravobot.news",
        "mas.to/zelenskyyua@zpravobot.news",
        "mstdn.social/zelenskyyua@zpravobot.news",
    ]
    canonical_ids = {bot_filter.canonical_account_id("mastodon", v) for v in variants}
    assert canonical_ids == {"zelenskyyua@zpravobot.news"}


def test_canonical_account_id_bluesky_is_unchanged():
    # Bluesky's author_id is already one global, source-agnostic identity
    # (a bare DID) -- Jetstream is a single firehose, not N independently
    # polled instances, so there's nothing to canonicalize.
    assert bot_filter.canonical_account_id("bluesky", "did:plc:abc123") == "did:plc:abc123"


def test_score_bot_velocity_unifies_across_polled_instances_for_the_same_account():
    # Before the fix, this exact scenario (one real account posting
    # rapidly but observed under N different polled-instance-prefixed
    # author_ids) would split into N separate low counts, none reaching
    # BOT_FILTER_VELOCITY_THRESHOLD (15) -- a genuinely high-frequency
    # poster looking like several low-frequency ones.
    index = InMemoryBotFilterIndex()
    instances = ["fosstodon.org", "hachyderm.io", "mas.to"]

    for i in range(20):
        author_id = f"{instances[i % len(instances)]}/crossposter@home.example"
        last = bot_filter.score_bot("mastodon", author_id, f"update {i}", uuid4(), index)

    assert last.velocity_component == 1.0
    # Confirms the counter really is shared, not 3 separate ones that each
    # happened to reach 1.0 independently.
    assert index.velocity == {"crossposter@home.example": 20}


def test_score_bot_normal_post_is_not_flagged():
    index = InMemoryBotFilterIndex()
    result = bot_filter.score_bot(
        source="bluesky",
        author_id="alice",
        text="had a lovely walk in the park this morning",
        cluster_id=uuid4(),
        index=index,
    )
    assert result.is_bot is False
    assert result.bot_score < bot_filter.BOT_FILTER_BOT_SCORE_THRESHOLD


def test_score_bot_rapid_fire_posting_raises_velocity_component():
    # velocity alone, even maxed out, is deliberately not enough to flag
    # is_bot on its own (weight 0.3 < threshold 0.5) — a genuinely active
    # human during breaking news shouldn't get flagged from this signal
    # alone. It should still visibly raise the score, though. Each post
    # uses different wording (varying the leading words, so the skeleton
    # differs too) so this isolates velocity from template_component --
    # a real busy human posts different updates each time, not identical
    # text, which is exactly what distinguishes this from the templated-bot
    # case below.
    index = InMemoryBotFilterIndex()
    author = "busy_human"

    first = bot_filter.score_bot("bluesky", author, "update 0: breaking news happening now", uuid4(), index)
    for i in range(1, 21):
        last = bot_filter.score_bot("bluesky", author, f"update {i}: breaking news happening now", uuid4(), index)

    assert last.velocity_component > first.velocity_component
    assert last.velocity_component == 1.0
    assert last.template_component < 1.0
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
        last = bot_filter.score_bot("bluesky", author, text, cluster_id, index)

    assert last.self_dup_component == 1.0
    assert last.velocity_component == 1.0
    assert last.is_bot is True


def test_score_bot_self_duplicate_flagged_on_second_post_into_same_cluster():
    index = InMemoryBotFilterIndex()
    author = "repeater"
    cluster_id = uuid4()

    first = bot_filter.score_bot("bluesky", author, "buy my product", cluster_id, index)
    second = bot_filter.score_bot("bluesky", author, "buy my product", cluster_id, index)

    assert first.self_dup_component == 0.0
    assert second.self_dup_component == 1.0


def test_score_bot_different_authors_same_cluster_not_self_duplicate():
    index = InMemoryBotFilterIndex()
    cluster_id = uuid4()

    result_a = bot_filter.score_bot("bluesky", "alice", "breaking news update", cluster_id, index)
    result_b = bot_filter.score_bot("bluesky", "bob", "breaking news update", cluster_id, index)

    assert result_a.self_dup_component == 0.0
    assert result_b.self_dup_component == 0.0


# --- template_skeleton / template_component (issue #40) ---

# Real reported posts -- whole-text Jaccard between these is ~0.01-0.13 via
# dedup.compute_minhash, nowhere near dedup's DEDUP_JACCARD_THRESHOLD=0.7,
# since the fixed template is short relative to the variable song/artist
# middle. template_skeleton catches it directly.
MIXIFY_A = "Now playing on Mixify Evergreen Hits: Hum To Tere Aashiq by Mukesh, Lata Mangeshkar! Tune in now: https://mixify.in"
MIXIFY_B = "Now playing on Mixify Bangla Hits: Nohe Nohe Prio by Asha Bhosle! Tune in now: https://mixify.in"
DFM_A = "Now playing on DFM: Unwritten by Natasha Bedingfield! Tune in now: https://a12.asurahosting.com/public/dfm"
DFM_B = "Now playing on DFM: Tika Taka Loka Tika Nilo Makata Niro 2026 by BeatWizzies! Tune in now: https://a12.asurahosting.com/public/dfm"

# Real production text (post-deploy, issue #40 follow-up): a second
# templated radio-bot account, jointil@mastodon.social, evaded the
# original 4-word-prefix/3-word-suffix window because it rotates across
# several named "stations", each with its own emoji landing exactly on
# word 4 and its own genre hashtag landing in the last 3 words.
JOINT_TRANCE = (
    "Now playing on 🎧 Joint Radio Beat Trance: 🎵 Echotek - Mini Pack This one is an absolute banger. "
    "Tune in: 🔊 https://www.jointil.com #Trance #ProgressiveTrance #Goa #PsyTrance #NowPlaying #Radio"
)
JOINT_REGGAE = (
    "Now playing on ❤️💛💚 Joint Radio Reggae: 🎵 Barrington Levy & Beenie Man - Under Me Sensi "
    "Just the right vibe for right now. Come listen: 🌴 https://www.jointil.com "
    "#Reggae #Roots #Dub #Rocksteady #NowPlaying #Radio"
)
JOINT_BLUES = (
    "Now playing on 🎸 Joint Radio Blues Rock: 🎵 The Beatles - Here Comes The Sun "
    "Perfect song for right now. Jump in the stream: https://www.jointil.com "
    "#Blues #Rock #BluesRock #classicRock #NowPlaying #Radio"
)


def test_template_skeleton_matches_same_stations_varying_songs():
    assert bot_filter.template_skeleton(MIXIFY_A) == bot_filter.template_skeleton(MIXIFY_B)
    assert bot_filter.template_skeleton(DFM_A) == bot_filter.template_skeleton(DFM_B)


def test_template_skeleton_matches_across_a_bots_rotating_stations():
    # The original gap: three different "stations" from the same account,
    # each with a different emoji (word 4) and genre hashtag (in the last
    # 3 words under the old window) -- the narrower 3-word-prefix/
    # 2-word-suffix window unifies them into one skeleton.
    assert (
        bot_filter.template_skeleton(JOINT_TRANCE)
        == bot_filter.template_skeleton(JOINT_REGGAE)
        == bot_filter.template_skeleton(JOINT_BLUES)
    )


def test_template_skeleton_differs_from_unrelated_content():
    # Different accounts landing on a similar skeleton (e.g. Mixify and
    # DFM both reducing to "now playing on || in now:") is fine, not a
    # bug -- bump_template_repeat is keyed by (author_id, skeleton), so
    # cross-account collisions were never a correctness risk. What still
    # matters is that the function isn't degenerate against genuinely
    # unrelated text.
    assert bot_filter.template_skeleton(MIXIFY_A) != bot_filter.template_skeleton(
        "had a lovely walk in the park this morning, the weather was perfect"
    )


def test_score_bot_repeated_template_flags_as_bot():
    # the templated-radio-bot pattern: varying song/artist each post, but
    # the same fixed "Now playing on X ... Tune in now: URL" wrapper --
    # dedup's self_dup_component never fires for this (see the Jaccard
    # numbers above), but template repetition should. template_component
    # alone maxes out after TEMPLATE_REPEAT_THRESHOLD (5) posts, but
    # crossing BOT_SCORE_THRESHOLD overall also needs velocity to climb
    # alongside it (confirmed by running this exact scenario: is_bot flips
    # to True at post 11) -- real templated bots post far more than that
    # within the 24h window, so 12 here is a realistic, not contrived, count.
    index = InMemoryBotFilterIndex()
    author = "mixify_radio"
    songs = [MIXIFY_A, MIXIFY_B] * 6  # 12 posts, alternating song, same skeleton

    for text in songs:
        last = bot_filter.score_bot("bluesky", author, text, uuid4(), index)

    assert last.template_component == 1.0
    assert last.self_dup_component == 0.0  # different clusters -- dedup never groups these
    assert last.is_bot is True


def test_score_bot_varying_structure_does_not_raise_template_component():
    index = InMemoryBotFilterIndex()
    author = "genuine_poster"
    texts = [
        "had a lovely walk in the park this morning",
        "tried a new recipe for dinner tonight, turned out great",
        "finally finished that book I've been reading for weeks",
    ]

    for text in texts:
        last = bot_filter.score_bot("bluesky", author, text, uuid4(), index)

    assert last.template_component < 1.0
    assert last.is_bot is False
