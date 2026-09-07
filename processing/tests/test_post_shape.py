from dataclasses import dataclass

from pipeline_stages import post_shape


@dataclass(frozen=True)
class Cfg:
    """Stand-in for db.PostShapeConfig (satisfies post_shape.ShapeConfig)."""

    enabled: bool = True
    devalue_multiplier: float = 0.3
    repeat_threshold: int | None = 3


# --- "nowplaying" shape: real production text (issue #189 corpus) ---

JOINT_REGGAE_1 = (
    "Now playing on ❤️ Joint Radio Reggae: \U0001f3b5 Al Campbell - Take A Ride "
    "listen with us \U0001f3a7 https://www.jointil.com #Reggae #AlCampbell"
)
JOINT_REGGAE_2 = (
    "Now playing on \U0001f49b\U0001f49a Joint Radio Reggae: \U0001f3b5 Barrington Levy - Under Me Sensi "
    "come listen \U0001f334 https://www.jointil.com #Roots #Dub #BarringtonLevy"
)
HOT21 = (
    "▶️ #NowPlaying on Hot 21 Radio: 93 'Til Infinity by Souls of Mischief \U0001f525 "
    "Tune in now: https://www.hot21radio.com #Hot21Radio #HipHop #RnB"
)
BBC = "BBC Radio 1 Anthems Radio 1 Anthems: Bloc Party, Miley Cyrus, Linkin Park and more Now Playing Avicii Levels"
TIBR_STRUCTURED = (
    'Artist: "Chris Mauden" Support: "https://bandwagon.fm/x" Title: "Boxberg II" Album: "Boxberg" '
    "Station: The Indie Beat Radio - Tune in"
)

JUST_LIKED = "\U0001f3a7 Just liked: Sign of the Times by Harry Styles #NowPlaying #Spotify \U0001f344"
BARE_TAGS = "#NowPlaying #Madonna #BedtimeStories"
PODCAST = "In this case believe the Urban Legend and tune into the Final Girls podcast!!!!"
TUNE_IN_ON_YOUTUBE = "The first episode is out! Tune in on YouTube, Spotify & Apple Podcasts as they discuss the week"


def test_structured_nowplaying_matches_with_registry_defaults():
    for text in (JOINT_REGGAE_1, HOT21, BBC, TIBR_STRUCTURED):
        match = post_shape.classify(text)
        assert match is not None, text
        assert match.name == "nowplaying"
        assert match.devalue_multiplier == 0.3
        assert match.repeat_threshold == 3


def test_key_is_stable_across_a_stations_tracks():
    k1 = post_shape.classify(JOINT_REGGAE_1).key
    k2 = post_shape.classify(JOINT_REGGAE_2).key
    assert k1 == k2 != ""


def test_genuine_or_incidental_text_does_not_match():
    for text in (JUST_LIKED, BARE_TAGS, PODCAST, TUNE_IN_ON_YOUTUBE, ""):
        assert post_shape.classify(text) is None, text


def test_db_row_overrides_the_registry_literals():
    match = post_shape.classify(HOT21, {"nowplaying": Cfg(devalue_multiplier=0.5, repeat_threshold=10)})
    assert match.devalue_multiplier == 0.5
    assert match.repeat_threshold == 10


def test_disabled_shape_is_skipped():
    assert post_shape.classify(HOT21, {"nowplaying": Cfg(enabled=False)}) is None


def test_unknown_shape_name_in_config_is_ignored():
    match = post_shape.classify(HOT21, {"flight_tracker": Cfg(enabled=False)})
    assert match is not None and match.name == "nowplaying"
    assert match.devalue_multiplier == 0.3  # registry literal, no override for "nowplaying"


def test_devalue_only_shape_config_carries_null_threshold():
    match = post_shape.classify(HOT21, {"nowplaying": Cfg(repeat_threshold=None)})
    assert match.repeat_threshold is None
