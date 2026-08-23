from util import sentiment_model


def test_tokenize_lowercases_words():
    assert sentiment_model.tokenize("Happy Day") == ["happy", "day"]


def test_tokenize_collapses_urls_and_mentions():
    tokens = sentiment_model.tokenize("check https://example.com/x @friend now")
    assert sentiment_model.URL_TOKEN in tokens
    assert sentiment_model.USER_TOKEN in tokens
    assert "friend" not in tokens


def test_tokenize_keeps_hashtag_word_content():
    # Now achieved via _split_camel_hashtags rather than a dedicated
    # hashtag token-group -- see TestSplitCamelHashtags below.
    assert "blessed" in sentiment_model.tokenize("#blessed today")


def test_tokenize_preserves_emoticons():
    tokens = sentiment_model.tokenize("so happy :) great day :-(")
    assert ":)" in tokens
    assert ":-(" in tokens


def test_tokenize_preserves_heart_emoticon():
    assert "<3" in sentiment_model.tokenize("i love this <3")


def test_tokenize_empty_string():
    assert sentiment_model.tokenize("") == []


def test_tokenize_collapses_digits_to_num_token():
    tokens = sentiment_model.tokenize("I have 100 dollars and it is 2024")
    assert tokens == [
        "i",
        "have",
        sentiment_model.NUM_TOKEN,
        "dollars",
        "and",
        "it",
        "is",
        sentiment_model.NUM_TOKEN,
    ]


def test_tokenize_does_not_split_mentions_containing_digits():
    # Mentions are matched and swallowed whole by _TOKEN_RE's own mention
    # group before _split_camel_hashtags gets any chance to touch them --
    # there's no "#" for it to key off, unlike hashtags below.
    tokens = sentiment_model.tokenize("@user123")
    assert tokens == [sentiment_model.USER_TOKEN]


def test_tokenize_splits_hashtags_containing_digits():
    # issue #74: hashtags now go through the same camelCase/digit-boundary
    # splitter as util/text_normalize.py's split_camel_hashtags -- a
    # letter->digit transition is a split point, so "win2024" becomes
    # "win" + NUM_TOKEN rather than one glued out-of-vocabulary token.
    tokens = sentiment_model.tokenize("#win2024")
    assert tokens == [".", "win", sentiment_model.NUM_TOKEN]


def test_encode_pads_short_sequences():
    vocab = {sentiment_model.PAD_TOKEN: 0, sentiment_model.UNK_TOKEN: 1, "hello": 2}
    ids = sentiment_model.encode(["hello"], vocab)
    assert len(ids) == sentiment_model.MAX_SEQ_LEN
    assert ids[0] == 2
    assert ids[1:] == [0] * (sentiment_model.MAX_SEQ_LEN - 1)


def test_encode_truncates_long_sequences():
    vocab = {sentiment_model.PAD_TOKEN: 0, sentiment_model.UNK_TOKEN: 1, "word": 2}
    tokens = ["word"] * (sentiment_model.MAX_SEQ_LEN + 10)
    ids = sentiment_model.encode(tokens, vocab)
    assert len(ids) == sentiment_model.MAX_SEQ_LEN
    assert all(i == 2 for i in ids)


def test_encode_unknown_tokens_map_to_unk():
    vocab = {sentiment_model.PAD_TOKEN: 0, sentiment_model.UNK_TOKEN: 1}
    ids = sentiment_model.encode(["nonexistent"], vocab)
    assert ids[0] == 1


class TestSplitCamelHashtags:
    """issue #74: mirrors util/text_normalize.py's TestSplitCamelHashtags --
    same boundary logic, duplicated (not imported) into this pinned,
    zero-project-imports file. Keep these two test suites in sync by hand
    if the boundary regex ever changes in either place."""

    def test_splits_on_lowercase_to_uppercase_boundary(self):
        assert sentiment_model._split_camel_hashtags("#OfCourseItsGenocide") == ". Of Course Its Genocide"

    def test_splits_acronym_run_before_titlecase_word(self):
        assert sentiment_model._split_camel_hashtags("#NFLDraft") == ". NFL Draft"

    def test_splits_on_digit_boundaries(self):
        assert sentiment_model._split_camel_hashtags("#Top10Movies2026") == ". Top 10 Movies 2026"

    def test_preserves_original_casing_no_lowercasing(self):
        result = sentiment_model._split_camel_hashtags("#TerryPratchett")
        assert result == ". Terry Pratchett"
        assert "Terry" in result  # not lowercased -- tokenize() does that itself, after this runs

    def test_leaves_non_hashtag_text_untouched(self):
        assert sentiment_model._split_camel_hashtags("no hashtags here at all") == "no hashtags here at all"

    def test_inserts_boundary_even_for_a_single_word_hashtag(self):
        assert sentiment_model._split_camel_hashtags("#food and #fun") == ". food and . fun"

    def test_known_limitation_two_letter_acronym_before_lowercase_word(self):
        # Same documented, accepted gap as text_normalize.py's version: no
        # case transition marks where "news" starts, so this splits the
        # acronym's own letters apart instead.
        assert sentiment_model._split_camel_hashtags("#UKnews") == ". U Knews"

    def test_tokenize_integration_splits_camel_hashtag_into_separate_word_tokens(self):
        # End-to-end through the real tokenizer, confirming the split words
        # flow into the ordinary lowercased `word` token path -- not just
        # that the standalone helper works in isolation.
        tokens = sentiment_model.tokenize("Great cast announcement #TomHanks #MerylStreep")
        assert tokens == [
            "great",
            "cast",
            "announcement",
            ".",
            "tom",
            "hanks",
            ".",
            "meryl",
            "streep",
        ]
