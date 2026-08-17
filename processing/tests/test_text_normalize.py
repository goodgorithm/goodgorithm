from util.text_normalize import normalize_text


def test_lowercases_text():
    assert normalize_text("Hello World") == "hello world"


def test_strips_urls():
    assert normalize_text("check https://example.com/path?x=1 out") == "check out"


def test_strips_mentions_including_dotted_handles():
    assert normalize_text("hey @friend.bsky.social nice") == "hey nice"


def test_collapses_whitespace():
    assert normalize_text("too   many\n\nspaces") == "too many spaces"


def test_strips_leading_and_trailing_whitespace():
    assert normalize_text("  padded  ") == "padded"


def test_empty_string():
    assert normalize_text("") == ""


def test_leaves_hashtags_and_ordinary_punctuation_untouched():
    assert normalize_text("So #blessed today!") == "so #blessed today!"
