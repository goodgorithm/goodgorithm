"""Rule-based category assignment -- classical lookup-table matching, no LLM,
per CLAUDE.md's no-LLM-in-the-algorithm constraint.

As of the trained category classifier (issue #34), this module is no longer
the primary categorization mechanism -- it's the whole-process fallback for
when the classifier can't load (R2 unconfigured, network failure, etc.),
the direct parallel to VADER's role for the sentiment CNN. It covers the
same 8-category set the classifier does, not a superset -- animals,
kindness_community, and environment_nature were deliberately dropped from
the taxonomy entirely rather than kept alive here at very low volume (see
CLAUDE.md's Category filtering section).

Two matching modes, not one, because of a real limitation found during the
original research pass: the pipeline's TF-IDF terms are unigrams only
(changing that would touch the live topicality/ranking signal, out of scope
here), so a phrase like "farmers market" can never appear whole in
`top_terms` -- only "farmers" and "market" separately, which is too broad on
its own. CATEGORY_TERMS matches single words/entities via set intersection;
CATEGORY_PHRASES matches multi-word phrases via substring against the post's
normalized text directly.

Known, accepted limitation, same "precision over recall, iterate later"
spirit as content_filter.py: this doesn't attempt span-level entity
disambiguation, and being a fallback path only (not the primary mechanism
anymore), it hasn't had the same depth of production-sample research the
original 8-category version got -- it only needs to be a reasonable safety
net, not the main event.
"""

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

# Tie-break order when a post scores equally across categories. No
# dedicated production-sample research pass behind this ordering (unlike
# the original 8, which had one) -- this module is a fallback now, not the
# primary path, so a reasonable order is enough.
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
    as tie-break. None means nothing matched -- expected for a large share of
    posts, same as the primary classifier's own confidence-threshold "none of
    these" case."""
    candidate_terms = set(entities) | set(top_terms)

    scores: dict[str, int] = {}
    for category in CATEGORY_PRIORITY:
        term_hits = len(candidate_terms & CATEGORY_TERMS.get(category, set()))
        phrase_hits = sum(1 for phrase in CATEGORY_PHRASES.get(category, set()) if phrase in normalized_text)
        scores[category] = term_hits + phrase_hits

    best = max(CATEGORY_PRIORITY, key=lambda c: (scores[c], -CATEGORY_PRIORITY.index(c)))
    return best if scores[best] > 0 else None
