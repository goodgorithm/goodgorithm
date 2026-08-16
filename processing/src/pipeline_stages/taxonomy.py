"""Rule-based category assignment -- classical lookup-table matching, no LLM,
per CLAUDE.md's no-LLM-in-the-algorithm constraint.

The whole-process fallback for when category_model.py's trained classifier
can't load, the direct parallel to VADER's role for the sentiment CNN --
same 8-category set the classifier uses, not a superset. See CLAUDE.md's
Category filtering section for why these 8 and not others, and the wiki's
Categorization page for this module's matching mechanics (why two matching
modes, known limitations)."""

CATEGORY_TERMS: dict[str, set[str]] = {
    "science_technology": {
        "opensource",
        "open-source",
        "github",
        "linux",
        "developer",
        "software",
        "startup",
        "browser",
        "kernel",
        "python",
        "javascript",
        "framework",
        "repository",
        "app",
        "ai",
        "llm",
        "openai",
        "anthropic",
        "chatgpt",
        "scientist",
        "scientists",
        "researcher",
        "researchers",
        "nasa",
        "telescope",
        "astronomy",
        "astronomer",
        "biology",
        "physics",
        "chemistry",
        "observatory",
        "discovery",
    },
    "sports": {
        "championship",
        "olympics",
        "olympic",
        "tournament",
        "medal",
        "athlete",
        "athletes",
        "marathon",
        "coach",
    },
    "health_fitness": {
        "hospital",
        "surgery",
        "vaccine",
        "vaccination",
        "diagnosis",
        "healthcare",
        "gym",
        "workout",
        "fitness",
        "yoga",
        "nutrition",
        "wellness",
    },
    "arts_culture": {
        "museum",
        "concert",
        "exhibit",
        "exhibition",
        "gallery",
        "theatre",
        "theater",
        "festival",
        "artist",
        "album",
        "novel",
        "painting",
        "sculpture",
        "orchestra",
        "poetry",
        "film",
        "cinema",
        "music",
        "song",
        "musician",
        "movie",
        "soundtrack",
    },
    "learning_education": {
        "scholarship",
        "university",
        "professor",
        "curriculum",
        "classroom",
        "literacy",
        "tutoring",
        "graduation",
        "textbook",
        "teacher",
    },
    "food_dining": {
        "recipe",
        "restaurant",
        "chef",
        "cuisine",
        "bakery",
        "brewery",
        "culinary",
        "cookbook",
    },
    "travel_adventure": {
        "backpacking",
        "itinerary",
        "expedition",
        "hiking",
        "trekking",
        "wanderlust",
        "passport",
        "hostel",
    },
    "gaming": {
        "esports",
        "playstation",
        "xbox",
        "nintendo",
        "speedrun",
        "multiplayer",
        "gamer",
        "videogame",
        "twitch",
    },
}

# Multi-word, matched as substrings of the post's normalize_text()'d text --
# for terms that are only unambiguous as a phrase (see module docstring).
CATEGORY_PHRASES: dict[str, set[str]] = {
    "health_fitness": {
        "cancer remission",
        "in remission",
        "medical breakthrough",
        "successful surgery",
        "organ transplant",
    },
    "food_dining": {
        "farmers market",
        "food truck",
    },
    "travel_adventure": {
        "road trip",
    },
    "gaming": {
        "video game",
        "video games",
    },
}

# Tie-break order when a post scores equally across categories -- a
# reasonable order is enough for a fallback path. See the wiki's
# Categorization page.
CATEGORY_PRIORITY: list[str] = [
    "science_technology",
    "health_fitness",
    "arts_culture",
    "learning_education",
    "food_dining",
    "travel_adventure",
    "gaming",
    "sports",
]


def categorize(entities: list[str], top_terms: list[str], normalized_text: str) -> str | None:
    """Highest-scoring category by (term hits + phrase hits), CATEGORY_PRIORITY
    as tie-break. None means nothing matched. See the wiki's Categorization
    page."""
    candidate_terms = set(entities) | set(top_terms)

    scores: dict[str, int] = {}
    for category in CATEGORY_PRIORITY:
        term_hits = len(candidate_terms & CATEGORY_TERMS.get(category, set()))
        phrase_hits = sum(1 for phrase in CATEGORY_PHRASES.get(category, set()) if phrase in normalized_text)
        scores[category] = term_hits + phrase_hits

    best = max(CATEGORY_PRIORITY, key=lambda c: (scores[c], -CATEGORY_PRIORITY.index(c)))
    return best if scores[best] > 0 else None
