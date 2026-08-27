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


def test_is_english_lang_tag():
    assert language_filter.is_english_lang_tag("en") is True
    assert language_filter.is_english_lang_tag("en-US") is True
    assert language_filter.is_english_lang_tag("EN-GB") is True
    assert language_filter.is_english_lang_tag("es") is False
    assert language_filter.is_english_lang_tag("eng") is False  # not a BCP-47 primary subtag
    assert language_filter.is_english_lang_tag("") is False
    assert language_filter.is_english_lang_tag(None) is False


def test_is_predominantly_non_latin_true_for_non_latin_scripts():
    assert language_filter.is_predominantly_non_latin("ขอเลื่อนไลฟ์เปิดกล้องมาเร็วขึ้น") is True  # Thai
    assert language_filter.is_predominantly_non_latin("もう今日なんも食えねえや") is True  # Japanese
    assert language_filter.is_predominantly_non_latin("увеличение государственного долга") is True  # Russian
    assert language_filter.is_predominantly_non_latin("سیرت النبی کانفرنس") is True  # Urdu


def test_is_predominantly_non_latin_false_for_latin_including_accented():
    assert language_filter.is_predominantly_non_latin("Beautiful sunset tonight over the bay.") is False
    assert language_filter.is_predominantly_non_latin("Creo que es la mejor de la tarde.") is False  # Spanish
    assert language_filter.is_predominantly_non_latin("Die Krähen haben Logenplätze ergattert.") is False  # German


def test_is_predominantly_non_latin_ignores_urls_mentions_hashtags_and_emoji():
    # The reported example from issue #105: a Thai livestream announcement
    # self-tagged `langs:["en"]`, whose Latin content is a link, a couple
    # of romanized names and ASCII hashtags.
    text = (
        "ขอเลื่อนไลฟ์เปิดกล้องมาเร็วขึ้น 1 วันนะคะ กลัวจะยังเจ็บนิ้วโป้งอยู่ "
        "แล้วก็วันนี้อาจจะเอาของที่ได้รับก่อนหน้ามาอวด ๆ ย้อนหลังด้วยย เจอกันนะ !\n\n"
        "【เปิดกล้อง】 แกะของขวัญจากงาน V:WØRLD #3 ตื่นเต้นน 【 Shogo VZ 】\n"
        "🗓️27/08/2026 |⏰20:00\n\nhttps://youtube.com/live/Pn2bYM6LvOI\n\n#Shog0Live #Vtuber #FreeTalk"
    )
    assert language_filter.is_predominantly_non_latin(text) is True
    # Inverse: English body carrying a non-Latin hashtag/mention is not flagged.
    assert language_filter.is_predominantly_non_latin("Great show tonight! #東京 @friend.bsky.social") is False


def test_is_predominantly_non_latin_false_for_no_letters():
    assert language_filter.is_predominantly_non_latin("") is False
    assert language_filter.is_predominantly_non_latin("😀🎉 123 !!! https://example.com") is False


def test_bluesky_tag_needs_recheck():
    # Primary self-report isn't English (langs:["es","en"] -> lang "es"):
    # ingestion kept it because "en" was in the array, so re-check.
    assert language_filter.bluesky_tag_needs_recheck("es", "Creo que es la mejor de la tarde.") is True
    # Tagged "en" but non-Latin body -> re-check (the #105 leak).
    assert language_filter.bluesky_tag_needs_recheck("en", "もう今日なんも食えねえや 一個1700kcal") is True
    # Tagged "en", Latin-script body -> trusted, no re-check (this is the
    # deliberately-open gap: short/casual English must not be re-checked).
    assert language_filter.bluesky_tag_needs_recheck("en", "im so excited hehe") is False
    assert language_filter.bluesky_tag_needs_recheck("en-US", "Pizza night!") is False
