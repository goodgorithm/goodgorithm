import os
import re

import spacy

from util.text_normalize import split_camel_hashtags

# Named-entity extraction (spaCy NER) feeding MMR's diversity term in
# ranking.py via RankablePost.entities -- see the wiki's Ranking page.

# Entity types that plausibly name a subject, not just calendar/quantity
# noise (DATE, CARDINAL, MONEY, PERCENT, etc. excluded by default).
RELEVANT_ENTITY_LABELS = frozenset(
    v.strip()
    for v in os.environ.get("RELEVANT_ENTITY_LABELS", "PERSON,ORG,GPE,LOC,FAC,EVENT,NORP,WORK_OF_ART").split(",")
    if v.strip()
)

_URL_ENTITY_RE = re.compile(r"^https?://\S+$")

_nlp: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        # Only doc.ents is ever read - the parser/tagger/attribute_ruler are
        # independent pipeline components that don't feed NER (they share
        # tok2vec's embeddings, not each other's output), so they run
        # unconditionally on every post's text for zero benefit unless
        # disabled too.
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "parser", "tagger", "attribute_ruler"])
    return _nlp


def _entities_from_doc(doc: spacy.tokens.Doc) -> list[str]:
    seen: dict[str, None] = {}
    for ent in doc.ents:
        if ent.label_ not in RELEVANT_ENTITY_LABELS:
            continue
        normalized = ent.text.strip().lower()
        # spaCy's NER occasionally mis-tags a URL span as a relevant label
        # (ORG/GPE are the ones seen in practice) -- a URL is never a
        # meaningful entity.
        if normalized and not _URL_ENTITY_RE.match(normalized):
            seen.setdefault(normalized)
    return list(seen)


def extract_entities_batch(texts: list[str]) -> list[list[str]]:
    """Lowercased entity texts per input text, deduped within each text in
    first-seen order. Runs the whole batch through nlp.pipe() in one call.
    Applies split_camel_hashtags only, not normalize_text -- NER needs the
    original casing that normalize_text() lowercases away."""
    return [_entities_from_doc(doc) for doc in _get_nlp().pipe(split_camel_hashtags(t) for t in texts)]
