import sentiment


def test_score_sentiment_clearly_positive():
    score = sentiment.score_sentiment("I love this, it's absolutely wonderful and amazing!")
    assert score > 0.5


def test_score_sentiment_clearly_negative():
    score = sentiment.score_sentiment("This is terrible, I hate it, everything is awful.")
    assert score < -0.5


def test_score_sentiment_neutral():
    score = sentiment.score_sentiment("The meeting is scheduled for 3pm on Tuesday.")
    assert -0.2 < score < 0.2


def test_score_sentiment_bounded():
    assert -1.0 <= sentiment.score_sentiment("great") <= 1.0
    assert -1.0 <= sentiment.score_sentiment("terrible") <= 1.0


def test_score_sentiment_empty_text():
    assert sentiment.score_sentiment("") == 0.0
