"""설정된 provider로 클립들을 인식."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .. import media
from .acrcloud import ACRCloudRecognizer
from .base import Match, Recognizer
from .shazam import ShazamRecognizer
from .vote import vote

log = logging.getLogger(__name__)


def recognizers() -> list[Recognizer]:
    rs: list[Recognizer] = []
    acr = ACRCloudRecognizer.from_env()
    if acr:
        rs.append(acr)
    try:
        rs.append(ShazamRecognizer())
    except Exception as e:  # shazamio 설치/호환 문제
        log.warning("Shazam 사용 불가: %s", e)
    return rs


async def _try(r: Recognizer, clip: Path | None, errors: list[str]) -> Match | None:
    if clip is None:
        return None
    try:
        return await r.recognize(clip)
    except Exception as e:
        errors.append(f"{r.name}: {e}")
        return None
    finally:
        await asyncio.sleep(0.5)  # 비공식 API 과호출 방지


async def recognize_clips(clips: list[Path]) -> dict:
    """구간마다 원본과 관중 소음을 줄인 버전을 모두 인식.

    라이브/직캠은 어느 쪽이 맞을지 구간마다 달라서 둘 다 본다.
    투표는 구간당 1표(원본 우선), 메들리 목록(songs)에는 양쪽에서 잡힌 곡을 모두 넣는다.
    """
    errors: list[str] = []
    for r in recognizers():
        per_clip: list[Match | None] = []
        heard: list[Match] = []          # 시간순, 양쪽 결과 모두
        for clip in clips:
            raw = await _try(r, clip, errors)
            dn_path = await asyncio.to_thread(media.denoise_clip, clip)
            dn = await _try(r, dn_path, errors)
            if dn:
                dn.extra["denoised"] = True
            per_clip.append(raw or dn)
            # 같은 구간에서 같은 곡이면 한 번만 (songs의 votes = 잡힌 구간 수)
            heard += [m for m in (raw, dn) if m and not (m is dn and raw and raw.key() == dn.key())]
        v = vote(per_clip, len(clips))
        v["songs"] = vote(heard, len(heard))["songs"]
        if v["match"]:
            v["provider"] = r.name
            v["errors"] = errors
            return v
    return {"match": None, "votes": 0, "total": len(clips), "confidence": "none",
            "alternatives": [], "songs": [], "provider": None, "errors": errors}
