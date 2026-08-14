from text_normalize import normalize_text

import taxonomy


def test_categorize_matches_single_term_via_entities_or_top_terms():
    assert taxonomy.categorize(["nasa"], [], normalize_text("text")) == "science_technology"
    assert taxonomy.categorize([], ["opensource"], normalize_text("text")) == "science_technology"


def test_categorize_returns_none_when_nothing_matches():
    # expected for a large share of posts, by design -- political/generic
    # content stays visible only in the unfiltered feed, never a category.
    assert taxonomy.categorize(["trump"], ["election"], normalize_text("a political post")) is None


def test_categorize_matches_health_fitness_term_and_phrase():
    term = normalize_text("Back at the gym after a long week")
    assert taxonomy.categorize([], ["gym"], term) == "health_fitness"

    phrase = normalize_text("Full House cast reunion since announced cancer remission")
    assert taxonomy.categorize([], ["reunion"], phrase) == "health_fitness"


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


def test_categorize_matches_travel_adventure_term_and_phrase():
    term = normalize_text("Started backpacking through the mountains today")
    assert taxonomy.categorize([], ["backpacking"], term) == "travel_adventure"

    phrase = normalize_text("Took an unforgettable road trip down the coast")
    assert taxonomy.categorize([], [], phrase) == "travel_adventure"


def test_categorize_matches_gaming_term_and_phrase():
    term = normalize_text("Local esports team just won the tournament")
    assert taxonomy.categorize([], ["esports"], term) == "gaming"

    phrase = normalize_text("Finally beat that video game after months of trying")
    assert taxonomy.categorize([], [], phrase) == "gaming"


def test_categorize_matches_learning_education_term():
    text = normalize_text("Professor announces new scholarship for first-gen students")
    assert taxonomy.categorize([], ["professor", "scholarship"], text) == "learning_education"


def test_categorize_matches_sports_term():
    text = normalize_text("Athlete wins gold medal at the olympics")
    assert taxonomy.categorize([], ["athlete", "medal", "olympics"], text) == "sports"


def test_categorize_score_ties_break_by_priority():
    assert taxonomy.CATEGORY_PRIORITY.index("science_technology") < taxonomy.CATEGORY_PRIORITY.index("sports")
