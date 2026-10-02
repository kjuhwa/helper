import pytest

from app import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(store, "_conn", None)
    yield
    if store._conn:
        store._conn.close()
    monkeypatch.setattr(store, "_conn", None)


def result(desc="원본 설명"):
    return {"meta": {"song": {"title_en": "Hype Boy", "artist_en": "NewJeans"},
                     "title_candidates": ["A", "B"], "description": desc,
                     "tags": ["뉴진스"], "hashtags": ["#NewJeans"], "category": "Music"},
            "source": {"title": "MV", "thumbnail": "http://t/x.jpg"}}


def test_save_list_search():
    aid = store.save_new(cache_key="k1", url="http://u", hint="하니", result=result())
    items = store.list_()
    assert items[0]["id"] == aid and items[0]["song"] == "NewJeans - Hype Boy"
    assert "result" not in items[0]
    assert store.list_(q="Hype")[0]["id"] == aid
    assert store.list_(q="없는말") == []
    assert store.find_by_cache_key("k1")["id"] == aid


def test_update_keeps_original_and_status():
    aid = store.save_new(cache_key="k", url="u", hint="", result=result())
    a = store.update(aid, meta={"description": "고친 설명", "selected_title": "B"},
                     status="uploaded", memo="메모")
    assert a["result"]["meta"]["description"] == "고친 설명"
    assert a["result"]["original_meta"]["description"] == "원본 설명"
    a = store.update(aid, meta={"description": "두번째"})
    assert a["result"]["original_meta"]["description"] == "원본 설명"
    assert a["status"] == "uploaded" and a["memo"] == "메모"
    assert store.list_(status="uploaded")[0]["id"] == aid
    with pytest.raises(ValueError):
        store.update(aid, status="bogus")


def test_delete():
    aid = store.save_new(cache_key="k", url="u", hint="", result=result())
    assert store.delete(aid) and store.get(aid) is None and not store.delete(aid)


def test_youtube_thumb():
    assert store.youtube_thumb("https://www.youtube.com/watch?v=11cta61wi0g&t=3").endswith("/11cta61wi0g/hqdefault.jpg")
    assert store.youtube_thumb("https://youtu.be/11cta61wi0g").endswith("/11cta61wi0g/hqdefault.jpg")
    assert store.youtube_thumb("https://www.youtube.com/shorts/abcdefghijk")
    assert store.youtube_thumb("https://instagram.com/p/x") == ""
