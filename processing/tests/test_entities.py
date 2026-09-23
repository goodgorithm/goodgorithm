import spacy

from pipeline_stages import entities


def test_extract_entities_finds_relevant_types_only():
    result = entities.extract_entities_batch(["NASA announced the discovery on March 3rd, with $500 million in funding."])
    assert result == [["nasa"]]


def test_extract_entities_empty_for_no_entities():
    assert entities.extract_entities_batch(["Local bakery wins a small business award this year."]) == [[]]


def test_extract_entities_dedupes_by_text():
    assert entities.extract_entities_batch(["NASA and NASA again announced the mission."]) == [["nasa"]]


def test_extract_entities_batch_keeps_per_text_results_separate():
    result = entities.extract_entities_batch(
        ["NASA announced the discovery today.", "Local bakery wins a small business award this year."]
    )
    assert result == [["nasa"], []]


def test_entities_from_doc_rejects_url_shaped_entities():
    # spaCy's NER occasionally mis-tags a URL span with a relevant label
    # (ORG/GPE seen in real production data) -- forces a URL entity via
    # doc.set_ents so this is deterministic regardless of what the real
    # model actually predicts for this input.
    nlp = entities._get_nlp()
    doc = nlp("Check out https://example.com/story for more")
    url_token_idx = next(i for i, t in enumerate(doc) if t.text.startswith("https"))
    span = spacy.tokens.Span(doc, url_token_idx, url_token_idx + 1, label="ORG")
    doc.set_ents([span])

    assert entities._entities_from_doc(doc) == []


def test_extract_entities_splits_adjacent_camel_case_hashtags_into_separate_entities():
    # Without split_camel_hashtags, adjacent glued hashtags confuse spaCy's
    # NER into merging or dropping entities -- the raw glued form only
    # recovers one of three names, while the split form recovers all three.
    result = entities.extract_entities_batch(["Great cast announcement #TomHanks #MerylStreep #DenzelWashington"])
    assert result == [["tom hanks", "meryl streep", "denzel washington"]]
