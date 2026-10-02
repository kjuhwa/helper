"""URL 영상 다운로드 (yt-dlp: 유튜브, 인스타그램, 틱톡, X, 직접 링크 등)."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .media import ffmpeg_exe


log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


# 유튜브가 연속 다운로드 중 가끔 403(Forbidden)/429로 막을 때: 간격을 두고 재시도 (대기초, 추가 옵션)
# 2026-10 기준 yt-dlp 기본 클라이언트(visionos) 외의 player_client는 모두 실패해서
# 클라이언트를 바꾸지 않고 기다렸다가 같은 방식으로 다시 받는다.
_ATTEMPTS: list[tuple[int, dict]] = [
    (0, {}),
    (8, {}),
    (20, {"format": "bv*+ba/b"}),   # 마지막엔 화질 제한 없이
]
_RETRYABLE = ("403", "429", "Forbidden", "Too Many Requests", "unable to download video data",
              "HTTP Error 5", "timed out", "Connection reset")


def is_retryable(msg: str) -> bool:
    return any(k in msg for k in _RETRYABLE)


def download(url: str, out_dir: Path, max_height: int = 720) -> tuple[Path, dict]:
    """영상을 받아 (파일 경로, 페이지 메타데이터)를 돌려준다.

    분석에는 고화질이 필요 없으므로 720p 이하로 받는다.
    403 같은 일시적인 거부는 접속 방식을 바꿔 최대 3번까지 시도한다.
    """
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "outtmpl": str(out_dir / "input.%(ext)s"),
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    last, tries = "", 0
    for i, (wait, extra) in enumerate(_ATTEMPTS):
        if i and not is_retryable(last):
            break  # 비공개·삭제·지역 제한 등은 재시도해도 소용없음
        if wait:
            log.info("다운로드 재시도 %d/%d (%ds 후): %s", i + 1, len(_ATTEMPTS), wait, url)
            time.sleep(wait)
        tries += 1
        for f in out_dir.glob("input.*"):  # 이전 시도의 조각 파일 정리
            f.unlink(missing_ok=True)
        try:
            with yt_dlp.YoutubeDL({**base, **extra}) as ydl:
                if i:
                    ydl.cache.remove()  # 오래된 서명 캐시가 403 원인일 때가 있음
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
        except Exception as e:
            last = str(e)
            continue
        if not path.exists():  # 병합 후 확장자가 바뀐 경우
            found = sorted(out_dir.glob("input.*"))
            if not found:
                last = "다운로드한 파일을 찾을 수 없습니다."
                continue
            path = found[0]
        return path, page_meta(info)
    tried = f" ({tries}번 시도)" if tries > 1 else ""
    raise DownloadError(f"영상을 받지 못했습니다{tried}: {last}")


PLAYLIST_MAX = int(os.getenv("HELPER_PLAYLIST_MAX", "100"))


_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com")


def normalize_video_url(url: str) -> str:
    """같은 영상이 같은 주소가 되도록 정리 (유튜브: watch?v=ID 만 남김)."""
    u = urlparse(url.strip())
    host = u.netloc.lower()
    vid = ""
    if host in _YT_HOSTS:
        q = parse_qs(u.query)
        if u.path == "/watch" and q.get("v"):
            vid = q["v"][0]
        elif u.path.startswith(("/shorts/", "/live/", "/embed/")):
            vid = u.path.split("/")[2]
    elif host in ("youtu.be", "www.youtu.be"):
        vid = u.path.lstrip("/").split("/")[0]
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return url.strip()


def is_mixed_url(url: str) -> bool:
    """영상 + 재생목록이 함께 든 주소 (예: watch?v=...&list=...)."""
    q = parse_qs(urlparse(url).query)
    return "v" in q and "list" in q


def expand_playlist(url: str, whole_playlist: bool = False) -> dict | None:
    """재생목록이면 {title, count, entries:[{url,title}]}, 단일 영상이면 None.

    watch?v=...&list=... 주소는 whole_playlist=True 일 때만 재생목록으로 본다.
    """
    import yt_dlp

    if is_mixed_url(url) and not whole_playlist:
        return None
    opts = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True,
            "noplaylist": False, "playlistend": PLAYLIST_MAX}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise DownloadError(f"URL 정보를 읽지 못했습니다: {e}") from e
    if not info or info.get("_type") != "playlist":
        return None
    entries = []
    for e in info.get("entries") or []:
        if not e:
            continue
        vurl = e.get("url") or e.get("webpage_url") or ""
        if not vurl.startswith("http") and e.get("id") and "youtube" in (e.get("ie_key") or "").lower():
            vurl = f"https://www.youtube.com/watch?v={e['id']}"
        if not vurl.startswith("http"):
            continue
        title = e.get("title") or ""
        if title in ("[Private video]", "[Deleted video]"):
            continue  # 비공개/삭제 영상은 분석 불가
        entries.append({"url": vurl, "title": title})
    if not entries:
        raise DownloadError("재생목록에 분석할 수 있는 영상이 없습니다.")
    return {"title": info.get("title") or "재생목록",
            "count": info.get("playlist_count") or len(entries),
            "entries": entries}


def page_meta(info: dict) -> dict:
    """곡 식별에 도움이 되는 원본 페이지 정보만 추린다."""
    return {
        "site": info.get("extractor_key") or "",
        "title": info.get("title") or "",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "description": (info.get("description") or "")[:1500],
        "tags": (info.get("tags") or [])[:30],
        "upload_date": info.get("upload_date") or "",
        "duration": info.get("duration") or 0,
        "webpage_url": info.get("webpage_url") or "",
        "thumbnail": info.get("thumbnail") or "",
        # 유튜브가 자체 인식한 음악 정보가 있으면 포함됨
        "track": info.get("track") or "",
        "artist": info.get("artist") or info.get("creator") or "",
        "album": info.get("album") or "",
    }
