"""shazamio(비공식 Shazam) 어댑터."""
from __future__ import annotations

from pathlib import Path

from .base import Match


class ShazamRecognizer:
    name = "shazam"

    def __init__(self) -> None:
        from pydub import AudioSegment
        from shazamio import Shazam

        from ..media import ffmpeg_exe

        AudioSegment.converter = ffmpeg_exe()  # PATH에 ffmpeg가 없어도 번들 바이너리 사용

        self._shazam = Shazam(language="ko-KR", endpoint_country="KR")

    async def recognize(self, clip: Path) -> Match | None:
        res = await self._shazam.recognize(str(clip))
        return parse_shazam(res)


def parse_shazam(res: dict) -> Match | None:
    track = (res or {}).get("track")
    if not track:
        return None
    meta: dict[str, str] = {}
    for section in track.get("sections", []):
        for m in section.get("metadata", []) or []:
            if m.get("title") and m.get("text"):
                meta[m["title"]] = m["text"]
    # 언어 설정에 따라 라벨이 한글/영문으로 올 수 있음
    album = meta.get("Album") or meta.get("앨범", "")
    released = meta.get("Released") or meta.get("발매", "") or meta.get("발매일", "")
    return Match(
        title=track.get("title", ""),
        artist=track.get("subtitle", ""),
        provider="shazam",
        album=album,
        release_date=released,
        isrc=track.get("isrc", "") or "",
        url=track.get("url", "") or "",
        extra={"label": meta.get("Label") or meta.get("레이블", ""),
               "genre": (track.get("genres") or {}).get("primary", "")},
    )
