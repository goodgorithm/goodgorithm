from pipeline_stages import language_filter


def test_detect_language_returns_empty_for_blank_text():
    assert language_filter.detect_language("") == ("", 0.0)
    assert language_filter.detect_language("   \n\n  ") == ("", 0.0)


def test_detect_language_identifies_clear_english():
    label, confidence = language_filter.detect_language(
        "The city council approved funding for three new community gardens this spring."
    )
    assert label == "en"
    assert confidence > language_filter.LANGUAGE_FILTER_CONFIDENCE_THRESHOLD


def test_detect_language_identifies_clear_non_english():
    label, confidence = language_filter.detect_language(
        "Die beiden Krähen auf dem Schornstein haben Logenplätze für die Sonnenfinsternis ergattert."
    )
    assert label == "de"
    assert confidence > language_filter.LANGUAGE_FILTER_CONFIDENCE_THRESHOLD


def test_is_non_english_false_for_english_text():
    assert language_filter.is_non_english("Beautiful sunset tonight, the whole sky turned orange.") is False


def test_is_non_english_true_for_confident_non_english_text():
    assert language_filter.is_non_english("もう今日なんも食えねえや 一個1700kcalのバーガーって") is True  # Japanese
    assert language_filter.is_non_english("Creo que es la mejor de la tarde.") is True  # Spanish


def test_is_non_english_false_for_blank_text():
    # Nothing to detect -- not confidently non-English, so kept (matches
    # this being a hard-exclude gate: no signal means no exclusion).
    assert language_filter.is_non_english("") is False
    assert language_filter.is_non_english("😀") is False
