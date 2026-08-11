"""Rule-based category assignment -- classical lookup-table matching, no LLM
and no trained classifier, per CLAUDE.md's no-LLM-in-the-algorithm
constraint. Term/phrase lists below are drafted from the 2026-08-11 taxonomy
research pass (real production sample posts, hand-read for coherence) --
see the Pre-v1 Roadmap's "Categories / topic filter view" item.

Two matching modes, not one, because of a real limitation found during that
research: the pipeline's TF-IDF terms are unigrams only (changing that would
touch the live topicality/ranking signal, out of scope here), so a phrase
like "solar power" can never appear whole in `top_terms` -- only "solar" and
"power" separately, which is too broad on its own (matched an astronomy
camera review, an EDM song title, and a watch review during research).
CATEGORY_TERMS matches single words/entities via set intersection;
CATEGORY_PHRASES matches multi-word phrases via substring against the
post's normalized text directly.

Known, accepted v1 limitation: this doesn't attempt span-level entity
disambiguation (e.g. "Nottingham Forest" the football club vs. "forest" the
habitat both contain "forest") -- bare terms prone to that kind of
proper-noun collision are deliberately left out rather than solved with
span-exclusion logic. Same "precision over recall, iterate later" spirit as
content_filter.py.
"""

CATEGORY_TERMS: dict[str, set[str]] = {
    "technology": {
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
    },
    "animals": {
        "wildlife",
        "zoo",
        "puppy",
        "puppies",
        "kitten",
        "kittens",
        "sanctuary",
        "veterinarian",
        "aquarium",
    },
    "science_discovery": {
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
    "kindness_community": {
        "volunteer",
        "volunteers",
        "charity",
        "nonprofit",
        "fundraiser",
        "neighbors",
        "generous",
    },
    "environment_nature": {
        "climate",
        "recycling",
        "conservation",
        "renewable",
        "sustainability",
        "ecosystem",
        "biodiversity",
        "reforestation",
        "rainforest",
    },
    "health_recovery": {
        "hospital",
        "surgery",
        "vaccine",
        "vaccination",
        "diagnosis",
        "healthcare",
    },
    "sports_achievement": {
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
}

# Multi-word, matched as substrings of the post's normalize_text()'d text --
# for terms that are only unambiguous as a phrase (see module docstring).
CATEGORY_PHRASES: dict[str, set[str]] = {
    "animals": {
        "animal rescue",
        "rescue dog",
        "rescue cat",
        "foster dog",
        "foster cat",
        "adopt dont shop",
    },
    "environment_nature": {
        "solar power",
        "solar powered",
        "solar-powered",
        "solar panel",
        "solar panels",
        "solar eclipse",
        "solar energy",
        "renewable energy",
        "clean energy",
        "climate change",
        "wildlife conservation",
    },
    "kindness_community": {
        "donated to charity",
        "charity donation",
        "donation drive",
        "community garden",
        "mutual aid",
        "food bank",
    },
    "health_recovery": {
        "cancer remission",
        "in remission",
        "medical breakthrough",
        "successful surgery",
        "organ transplant",
        "heart transplant",
        "kidney transplant",
        "clinical trial",
    },
}

# Tie-break order when a post scores equally across categories -- e.g. an AI
# model/company-product post matches both "technology" and
# "science_discovery" terms; research found these read better as technology.
CATEGORY_PRIORITY: list[str] = [
    "technology",
    "science_discovery",
    "animals",
    "environment_nature",
    "health_recovery",
    "kindness_community",
    "arts_culture",
    "sports_achievement",
]


def categorize(entities: list[str], top_terms: list[str], normalized_text: str) -> str | None:
    """Highest-scoring category by (term hits + phrase hits), CATEGORY_PRIORITY
    as tie-break. None means nothing matched -- expected for a large share of
    posts (political/generic content in particular, by design: it stays
    visible only in the unfiltered feed, never a named category)."""
    candidate_terms = set(entities) | set(top_terms)

    scores: dict[str, int] = {}
    for category in CATEGORY_PRIORITY:
        term_hits = len(candidate_terms & CATEGORY_TERMS.get(category, set()))
        phrase_hits = sum(1 for phrase in CATEGORY_PHRASES.get(category, set()) if phrase in normalized_text)
        scores[category] = term_hits + phrase_hits

    best = max(CATEGORY_PRIORITY, key=lambda c: (scores[c], -CATEGORY_PRIORITY.index(c)))
    return best if scores[best] > 0 else None
