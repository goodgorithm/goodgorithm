from util.text_normalize import normalize_text, split_camel_hashtags


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


def test_leaves_ordinary_punctuation_untouched():
    assert normalize_text("So great, today!") == "so great, today!"


def test_splits_camel_case_hashtag_before_lowercasing():
    assert normalize_text("So #ThisIsGreat today") == "so . this is great today"


def test_single_word_hashtag_gets_boundary_but_no_internal_split():
    # No camelCase boundary inside "blessed" -- just gets the leading ". "
    # separator, same as every other hashtag.
    assert normalize_text("So #blessed today!") == "so . blessed today!"


def test_normalize_text_camel_split_runs_before_lowercasing():
    # If split_camel_hashtags ran after lowercasing, this would stay glued
    # -- confirms normalize_text's ordering, not just split_camel_hashtags
    # in isolation.
    assert normalize_text("#OpenSourceAI") == ". open source ai"


class TestSplitCamelHashtags:
    def test_splits_on_lowercase_to_uppercase_boundary(self):
        assert split_camel_hashtags("#OfCourseItsGenocide") == ". Of Course Its Genocide"

    def test_splits_acronym_run_before_titlecase_word(self):
        assert split_camel_hashtags("#NFLDraft") == ". NFL Draft"

    def test_splits_on_digit_boundaries(self):
        assert split_camel_hashtags("#Top10Movies2026") == ". Top 10 Movies 2026"

    def test_preserves_original_casing_no_lowercasing(self):
        result = split_camel_hashtags("#TerryPratchett")
        assert result == ". Terry Pratchett"
        assert "Terry" in result  # not lowercased -- callers need this for NER

    def test_leaves_non_hashtag_text_untouched(self):
        assert split_camel_hashtags("no hashtags here at all") == "no hashtags here at all"

    def test_inserts_boundary_even_for_a_single_word_hashtag(self):
        # Load-bearing for preventing adjacent hashtags from merging into
        # one entity downstream (issue #70) -- applies uniformly, not just
        # to camelCase-shaped tags.
        assert split_camel_hashtags("#food and #fun") == ". food and . fun"

    def test_known_limitation_two_letter_acronym_before_lowercase_word(self):
        # Documented, accepted gap: no case transition marks where "news"
        # starts, so this splits the acronym's own letters apart instead.
        assert split_camel_hashtags("#UKnews") == ". U Knews"
