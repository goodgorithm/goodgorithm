from pipeline_stages import political_exclude

CLASSIFIER_THRESHOLD = political_exclude.POLITICAL_EXCLUDE_CLASSIFIER_THRESHOLD
CENTROID_THRESHOLD = political_exclude.POLITICAL_EXCLUDE_CENTROID_THRESHOLD


def test_excludes_when_both_signals_clear_threshold():
    assert political_exclude.is_political_excluded(CLASSIFIER_THRESHOLD, CENTROID_THRESHOLD)


def test_does_not_exclude_when_classifier_score_below_threshold():
    assert not political_exclude.is_political_excluded(CLASSIFIER_THRESHOLD - 0.01, CENTROID_THRESHOLD)


def test_does_not_exclude_when_centroid_score_below_threshold():
    assert not political_exclude.is_political_excluded(CLASSIFIER_THRESHOLD, CENTROID_THRESHOLD - 0.01)


def test_does_not_exclude_when_classifier_score_missing():
    assert not political_exclude.is_political_excluded(None, CENTROID_THRESHOLD)


def test_does_not_exclude_when_centroid_score_missing():
    assert not political_exclude.is_political_excluded(CLASSIFIER_THRESHOLD, None)


def test_does_not_exclude_when_both_scores_missing():
    assert not political_exclude.is_political_excluded(None, None)
