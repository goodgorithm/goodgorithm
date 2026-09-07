from pipeline_stages import nowplaying_demote

# Real production text (issue #189).
JOINT_REGGAE = (
    "Now playing on ❤️\U0001f49b\U0001f49a Joint Radio Reggae: \U0001f3b5 Al Campbell - Take A Ride "
    "Take a break and listen to some good roots with us \U0001f3a7 https://www.jointil.com "
    "#Reggae #AlCampbell #TakeARide"
)
HOT21 = (
    "▶️ #NowPlaying on Hot 21 Radio: 93 'Til Infinity by Souls of Mischief \U0001f525 "
    "Tune in now: https://www.hot21radio.com #Hot21Radio #HipHop #RnB"
)
PHOENIX_FM = (
    "\U0001f3b5 Now on Phoenix FM: Bounce, Rock, Skate, Roll (Remastered) by Vaughan Mason and Crew "
    "#NowPlaying #PhoenixFM"
)
BBC = "BBC Radio 1 Anthems Radio 1 Anthems: Bloc Party, Miley Cyrus, Linkin Park and more Now Playing Avicii Levels"
TIBR_STRUCTURED = (
    'Artist: "Chris Mauden" Support: "https://bandwagon.fm/x" Title: "Boxberg II" Album: "Boxberg" '
    "Station: The Indie Beat Radio - Tune in"
)

# Genuine humans / incidental matches -- must NOT be devalued.
JUST_LIKED = "\U0001f3a7 Just liked: Sign of the Times by Harry Styles #NowPlaying #Spotify \U0001f344"
BARE_TAGS = "#NowPlaying #Madonna #BedtimeStories"
PLAYLIST_SHARE = "Made a playlist of my favourite Dutch music of recent years. Listen here: https://x.club #nowplaying"
PODCAST = "In this case believe the Urban Legend and tune into the Final Girls podcast!!!!"
TUNE_IN_ON_YOUTUBE = "The first episode is out! Tune in on YouTube, Spotify & Apple Podcasts as they discuss the week"


def test_structured_nowplaying_post_is_devalued():
    for text in (JOINT_REGGAE, HOT21, PHOENIX_FM, BBC, TIBR_STRUCTURED):
        result = nowplaying_demote.classify(text)
        assert result.is_nowplaying is True, text
        assert result.devalue_multiplier == nowplaying_demote.NOWPLAYING_DEMOTE_MULTIPLIER
        assert 0.0 < result.devalue_multiplier < 1.0


def test_genuine_or_incidental_now_playing_text_is_untouched():
    for text in (JUST_LIKED, BARE_TAGS, PLAYLIST_SHARE, PODCAST, TUNE_IN_ON_YOUTUBE):
        result = nowplaying_demote.classify(text)
        assert result.is_nowplaying is False, text
        assert result.devalue_multiplier == 1.0


def test_empty_text_is_untouched():
    result = nowplaying_demote.classify("")
    assert result.is_nowplaying is False
    assert result.devalue_multiplier == 1.0
