from pipeline_stages import hashtag_bag


def test_pure_hashtag_bag_is_devalued():
    result = hashtag_bag.classify("#GrandCanyon #Arizona #Sunset #Orange #Trees #Beautiful")
    assert result.is_hashtag_bag is True
    assert result.devalue_multiplier == hashtag_bag.HASHTAG_BAG_DEVALUE_MULTIPLIER
    assert 0.0 < result.devalue_multiplier < 1.0


def test_one_word_plus_many_tags_is_devalued():
    result = hashtag_bag.classify(
        "worry #art #mastoArt #noAI #digitalArt #artist #artistsOnMastodon #fediArt #cute"
    )
    assert result.is_hashtag_bag is True


def test_self_promo_tag_run_is_devalued():
    result = hashtag_bag.classify(
        "#IndieAuthor #FantasyAuthor #DarkFiction #MonsterFiction #EpicFantasy #Suspense #Thriller"
    )
    assert result.is_hashtag_bag is True


def test_real_caption_with_a_few_tags_is_untouched():
    result = hashtag_bag.classify(
        "Beautiful shot today, the light over the ridge was completely unreal #photography #nature #wildlife"
    )
    assert result.is_hashtag_bag is False
    assert result.devalue_multiplier == 1.0


def test_two_topic_tags_is_below_the_minimum():
    result = hashtag_bag.classify("in my happy place #touhou #TouhouKoumakyou")
    assert result.is_hashtag_bag is False


def test_tags_do_not_outnumber_prose_is_untouched():
    # 3 prose words, 3 tags -> tags don't strictly outnumber -> not a bag
    result = hashtag_bag.classify("just having fun #oot #zelda #wip")
    assert result.is_hashtag_bag is False


def test_hashtag_bag_with_a_link_is_left_to_link_share():
    result = hashtag_bag.classify("_ #SQL #interview #DataScience https://www.instagram.com/p/abc")
    assert result.is_hashtag_bag is False
    result = hashtag_bag.classify("promo #a #b #c #d www.example.com/x")
    assert result.is_hashtag_bag is False


def test_genuine_short_warm_post_with_no_tags_is_untouched():
    result = hashtag_bag.classify("New Kirby? Looks cute!")
    assert result.is_hashtag_bag is False


def test_emoji_and_punctuation_do_not_count_as_prose():
    # only "Smile" is a prose word once emoji/punct are stripped
    result = hashtag_bag.classify("Smile 🌸✨!! #art #artwork #digitalart #oc")
    assert result.is_hashtag_bag is True


def test_camelcase_tag_is_not_expanded_into_prose_words():
    # #SocialMediaManagement must count as ONE hashtag, not inflate the
    # prose count the way util/text_normalize.split_camel_hashtags would
    result = hashtag_bag.classify(
        "TRESSO2 #TRESSO #SocialMediaManagement #SocialMediaScheduler #ContentCreator #ContentMarketing"
    )
    assert result.is_hashtag_bag is True


def test_non_ascii_hashtags_count():
    result = hashtag_bag.classify("OOOOH #ENHYPEN #엔하이픈 #THE_SIN_BLISS")
    assert result.is_hashtag_bag is True


def test_empty_and_none_text_are_safe():
    assert hashtag_bag.classify("").is_hashtag_bag is False
    assert hashtag_bag.classify(None).is_hashtag_bag is False
