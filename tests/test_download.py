import pytest
import yt_dlp

from app import download


class FakeYDL:
    calls = 0
    script = []          # 시도마다 낼 결과: 예외 메시지 또는 None(성공)

    def __init__(self, opts):
        self.opts = opts
        self.cache = type("C", (), {"remove": lambda self: None})()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        err = FakeYDL.script[FakeYDL.calls]
        FakeYDL.calls += 1
        if err:
            raise yt_dlp.utils.DownloadError(err)
        self.path = self.opts["outtmpl"].replace("%(ext)s", "mp4")
        open(self.path, "wb").write(b"x")
        return {"title": "t", "webpage_url": url}

    def prepare_filename(self, info):
        return self.path


@pytest.fixture
def fake(monkeypatch):
    FakeYDL.calls = 0
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    return FakeYDL


def test_retries_403_then_succeeds(fake, tmp_path):
    fake.script = ["ERROR: unable to download video data: HTTP Error 403: Forbidden", None]
    path, meta = download.download("https://y/v", tmp_path)
    assert path.exists() and fake.calls == 2 and meta["title"] == "t"


def test_gives_up_after_all_attempts(fake, tmp_path):
    fake.script = ["HTTP Error 403: Forbidden"] * 3
    with pytest.raises(download.DownloadError, match="3번 시도"):
        download.download("https://y/v", tmp_path)
    assert fake.calls == 3


def test_no_retry_for_private_video(fake, tmp_path):
    fake.script = ["ERROR: [youtube] x: Private video. Sign in", None]
    with pytest.raises(download.DownloadError) as e:
        download.download("https://y/v", tmp_path)
    assert fake.calls == 1 and "번 시도" not in str(e.value)
