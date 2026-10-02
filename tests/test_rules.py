from app import youtube_rules as yr


def test_tag_cost_counts_quotes_and_commas():
    assert yr.tags_total(["뉴진스", "NewJeans Fancam"]) == 3 + (15 + 2) + 1


def test_clean_tags_dedup_and_limit():
    tags = ["NewJeans", "newjeans", "#하니", "a<b>"] + [f"tag{i:03d}xxxxxxxxxx" for i in range(60)]
    out, warnings = yr.clean_tags(tags)
    assert out[:3] == ["NewJeans", "하니", "ab"]
    assert yr.tags_total(out) <= 500
    assert warnings


def test_title_trim_and_angle():
    t, w = yr.clean_title("<" + "가" * 120 + ">")
    assert len(t) == 100 and "<" not in t and w


def test_hashtags_no_space_limit():
    out, _ = yr.clean_hashtags(["뉴 진스", "#NewJeans", "newjeans"] + [f"h{i}" for i in range(30)])
    assert out[0] == "#뉴진스" and out[1] == "#NewJeans"
    assert len(out) == yr.HASHTAG_RECOMMENDED
