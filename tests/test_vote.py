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



def test_songs_lists_medley_in_order():
    v = vote([None, m("Stuck In The Middle"), m("Love, Maybe"), None, m("DREAM"), m("Love, Maybe")], 6)
    assert [s["title"] for s in v["songs"]] == ["Stuck In The Middle", "Love, Maybe", "DREAM"]
    assert v["match"]["title"] == "Love, Maybe" and v["songs"][1]["votes"] == 2
    assert vote([None], 1)["songs"] == []


def test_runner_counts_each_clip_once(monkeypatch, tmp_path):
    import asyncio
    from app.recognize import runner

    answers = {"c0": m("A"), "c0_dn": m("A"), "c1": None, "c1_dn": m("B"), "c2": m("A"), "c2_dn": m("C")}

    class Fake:
        name = "fake"
        async def recognize(self, clip):
            return answers[clip.stem]

    monkeypatch.setattr(runner, "recognizers", lambda: [Fake()])
    monkeypatch.setattr(runner.media, "denoise_clip", lambda c: c.with_name(c.stem + "_dn.wav"))
    real_sleep = asyncio.sleep
    monkeypatch.setattr(runner.asyncio, "sleep", lambda s: real_sleep(0))
    clips = [tmp_path / f"c{i}.wav" for i in range(3)]
    v = asyncio.run(runner.recognize_clips(clips))
    assert v["votes"] == 2 and v["match"]["title"] == "A"          # c0, c2
    assert [(s["title"], s["votes"]) for s in v["songs"]] == [("A", 2), ("B", 1), ("C", 1)]
