from pipeline_stages import quality_exclude

THRESHOLD = quality_exclude.QUALITY_EXCLUDE_THRESHOLD


def test_excludes_when_score_below_threshold():
    assert quality_exclude.is_quality_excluded(THRESHOLD - 0.01)


def test_does_not_exclude_when_score_at_threshold():
    assert not quality_exclude.is_quality_excluded(THRESHOLD)


def test_does_not_exclude_when_score_above_threshold():
    assert not quality_exclude.is_quality_excluded(THRESHOLD + 0.01)


def test_does_not_exclude_when_score_missing():
    assert not quality_exclude.is_quality_excluded(None)
