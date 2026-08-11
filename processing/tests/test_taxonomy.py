from dedup import normalize_text

import taxonomy


def test_categorize_matches_single_term_via_entities_or_top_terms():
    assert taxonomy.categorize(["nasa"], [], normalize_text("text")) == "science_discovery"
    assert taxonomy.categorize([], ["opensource"], normalize_text("text")) == "technology"


def test_categorize_returns_none_when_nothing_matches():
    # expected for a large share of posts, by design -- political/generic
    # content stays visible only in the unfiltered feed, never a category.
    assert taxonomy.categorize(["trump"], ["election"], normalize_text("a political post")) is None


def test_categorize_prioritizes_technology_over_science_for_ai_content():
    # real disambiguation case from the taxonomy research: AI/company-model
    # posts matched both categories' terms, read better as technology.
    text = normalize_text("Read more about Meta's new AI model release")
    assert taxonomy.categorize(["meta"], ["ai", "model"], text) == "technology"


def test_categorize_requires_phrase_not_bare_solar():
    # bare "solar" matched an astronomy-camera review, an EDM song title,
    # and a watch review during research -- deliberately not a term.
    bare = normalize_text("Top smart instruments: explore the cosmos with this solar-adjacent gadget")
    assert taxonomy.categorize([], ["solar", "gadget"], bare) is None

    phrase = normalize_text("Solar-powered coffee concept serving up good vibes")
    assert taxonomy.categorize([], ["coffee"], phrase) == "environment_nature"


def test_categorize_requires_phrase_not_bare_donate_for_kindness():
    # bare "donate" caught a partisan campaign-donation post during
    # research -- deliberately not a term, only specific charity phrases.
    political = normalize_text("Donate to Support a Candidate for Congress")
    assert taxonomy.categorize([], ["congress"], political) is None

    charity = normalize_text("Just backed this community fundraiser on Kickstarter")
    assert taxonomy.categorize([], ["fundraiser", "kickstarter"], charity) == "kindness_community"


def test_categorize_matches_health_recovery_phrase():
    text = normalize_text("Full House cast reunion since announced cancer remission")
    assert taxonomy.categorize([], ["reunion"], text) == "health_recovery"


def test_categorize_matches_animals_phrase_not_bare_rescue():
    # bare "rescue" matched aviation-tracker and fire-dispatch bot accounts
    # during research -- deliberately not a term, only "animal/dog/cat rescue".
    dispatch = normalize_text("Rescue Extrication at 25th Ave Ne / Ne 125th St")
    assert taxonomy.categorize([], [], dispatch) is None

    animal = normalize_text("Join Wags and Walks Nashville for animal rescue trivia night")
    assert taxonomy.categorize([], ["trivia"], animal) == "animals"


def test_categorize_score_ties_break_by_priority():
    # a post matching one term in each of two categories should resolve to
    # whichever comes first in CATEGORY_PRIORITY, not be arbitrary.
    assert taxonomy.CATEGORY_PRIORITY.index("technology") < taxonomy.CATEGORY_PRIORITY.index(
        "science_discovery"
    )
