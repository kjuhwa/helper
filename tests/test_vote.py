from app.media import clip_offsets
from app.recognize.base import Match
from app.recognize.shazam import parse_shazam
from app.recognize.vote import vote


def m(t, a="NewJeans", isrc=""):
    return Match(title=t, artist=a, provider="t", isrc=isrc)


def test_majority():
    v = vote([m("Supernatural"), None, m("Supernatural"), m("Hype Boy")], 4)
    assert v["match"]["title"] == "Supernatural" and v["votes"] == 2 and v["confidence"] == "high"
    assert v["alternatives"][0]["title"] == "Hype Boy"


def test_tie_prefers_earlier():
    v = vote([m("A"), m("B")], 2)
    assert v["match"]["title"] == "A" and v["confidence"] == "low"


def test_none():
    assert vote([None, None], 2)["confidence"] == "none"


def test_isrc_groups_different_titles():
    v = vote([m("Supernatural", isrc="X1"), m("슈퍼내추럴", isrc="x1")], 2)
    assert v["votes"] == 2


def test_parse_shazam():
    res = {"track": {"title": "Supernatural", "subtitle": "NewJeans", "isrc": "USX",
                     "sections": [{"metadata": [{"title": "Album", "text": "Supernatural"},
                                                {"title": "Released", "text": "2024"}]}]}}
    mt = parse_shazam(res)
    assert mt.album == "Supernatural" and mt.release_date == "2024"
    assert parse_shazam({"matches": []}) is None


def test_clip_offsets_skip_intro():
    offs = clip_offsets(200, 4, 12)
    assert offs[0] == 20.0 and len(offs) == 4 and offs[-1] <= 200 - 12
    assert clip_offsets(10) == [0.0]

