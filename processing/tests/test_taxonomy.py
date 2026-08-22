from util.text_normalize import normalize_text

from pipeline_stages import taxonomy


def test_categorize_matches_single_term_via_entities_or_top_terms():
    assert taxonomy.categorize(["nasa"], [], normalize_text("text")) == "science_technology"
    assert taxonomy.categorize([], ["opensource"], normalize_text("text")) == "science_technology"


def test_categorize_returns_none_when_nothing_matches():
    # expected for a large share of posts, by design -- political/generic
    # content stays visible only in the unfiltered feed, never a category.
    assert taxonomy.categorize(["trump"], ["election"], normalize_text("a political post")) is None


def test_categorize_matches_arts_culture_including_music_and_film():
    music = normalize_text("New album from a favorite musician just dropped")
    assert taxonomy.categorize([], ["album", "musician"], music) == "arts_culture"

    film = normalize_text("Caught a great movie at the local cinema tonight")
    assert taxonomy.categorize([], ["movie", "cinema"], film) == "arts_culture"


def test_categorize_matches_food_dining_term_and_phrase():
    term = normalize_text("This chef's new cuisine is incredible")
    assert taxonomy.categorize([], ["chef", "cuisine"], term) == "food_dining"

    phrase = normalize_text("Grabbed lunch from the food truck at the farmers market")
    assert taxonomy.categorize([], [], phrase) == "food_dining"


def test_categorize_matches_diaries_daily_life_phrase():
    # No CATEGORY_TERMS entry for this category (see taxonomy.py's comment) --
    # phrase-only matching.
    phrase = normalize_text("Good morning everyone, hope you have a great day")
    assert taxonomy.categorize([], [], phrase) == "diaries_daily_life"

    friday = normalize_text("Happy Friday to all my friends out there")
    assert taxonomy.categorize([], [], friday) == "diaries_daily_life"


def test_categorize_score_ties_break_by_priority():
    assert (
        taxonomy.CATEGORY_PRIORITY.index("science_technology")
        < taxonomy.CATEGORY_PRIORITY.index("diaries_daily_life")
    )
