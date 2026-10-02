from app import download, jobs


def test_mixed_url():
    assert download.is_mixed_url("https://www.youtube.com/watch?v=abc&list=PL1")
    assert not download.is_mixed_url("https://www.youtube.com/playlist?list=PL1")
    assert not download.is_mixed_url("https://www.youtube.com/watch?v=abc")


def test_batch_and_cancel():
    pl = {"title": "PL", "count": 3,
          "entries": [{"url": f"https://y/{i}", "title": f"v{i}"} for i in range(3)]}
    b = jobs.new_batch("https://y/pl", "힌트", pl)
    pub = b.public()
    assert pub["kind"] == "batch" and pub["total"] == 3 and not pub["finished"]
    assert all(i["status"] == "queued" for i in pub["items"])
    j0 = jobs.JOBS[b.job_ids[0]]
    assert j0.playlist == "PL" and j0.hint == "힌트" and j0.title == "v0"
    j0.status = "vision"  # 진행 중인 영상은 취소되지 않음
    assert jobs.cancel_batch(b) == 2
    pub = b.public()
    assert pub["canceled"] == 2 and not pub["finished"]
    j0.status = "done"
    assert b.public()["finished"]


def test_normalize_video_url():
    n = download.normalize_video_url
    want = "https://www.youtube.com/watch?v=11cta61wi0g"
    assert n("https://www.youtube.com/watch?v=11cta61wi0g&list=PL1&index=3") == want
    assert n("https://youtu.be/11cta61wi0g?si=abc") == want
    assert n("https://m.youtube.com/shorts/11cta61wi0g") == want
    assert n(" https://example.com/a.mp4 ") == "https://example.com/a.mp4"
    assert jobs.new_job("https://youtu.be/11cta61wi0g", "").cache_key == jobs.cache_key(want, "")


def test_retry_batch_resets_errors():
    pl = {"title": "PL", "count": 3, "entries": [{"url": f"https://y/r{i}", "title": f"r{i}"} for i in range(3)]}
    b = jobs.new_batch("https://y/plr", "", pl)
    a, c, d = (jobs.JOBS[j] for j in b.job_ids)
    a.status, a.error = "error", "403"
    c.status = "canceled"
    d.status = "done"
    assert [j.id for j in jobs.retry_batch(b)] == [a.id]
    assert a.status == "queued" and a.error == "" and c.status == "canceled"
    assert [j.id for j in jobs.retry_batch(b, include_canceled=True)] == [c.id]
