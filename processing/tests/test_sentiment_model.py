import sentiment_model


def test_tokenize_lowercases_words():
    assert sentiment_model.tokenize("Happy Day") == ["happy", "day"]


def test_tokenize_collapses_urls_and_mentions():
    tokens = sentiment_model.tokenize("check https://example.com/x @friend now")
    assert sentiment_model.URL_TOKEN in tokens
    assert sentiment_model.USER_TOKEN in tokens
    assert "friend" not in tokens


def test_tokenize_keeps_hashtag_word_content():
    assert "blessed" in sentiment_model.tokenize("#blessed today")


def test_tokenize_preserves_emoticons():
    tokens = sentiment_model.tokenize("so happy :) great day :-(")
    assert ":)" in tokens
    assert ":-(" in tokens


def test_tokenize_preserves_heart_emoticon():
    assert "<3" in sentiment_model.tokenize("i love this <3")


def test_tokenize_empty_string():
    assert sentiment_model.tokenize("") == []


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
