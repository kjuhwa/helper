"""설정된 provider로 클립들을 인식."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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


async def recognize_clips(clips: list[Path]) -> dict:
    errors: list[str] = []
    for r in recognizers():
        results: list[Match | None] = []
        for clip in clips:
            try:
                results.append(await r.recognize(clip))
            except Exception as e:
                errors.append(f"{r.name}: {e}")
                results.append(None)
            await asyncio.sleep(0.5)  # 비공식 API 과호출 방지
        v = vote(results, len(clips))
        if v["match"]:
            v["provider"] = r.name
            v["errors"] = errors
            return v
    return {"match": None, "votes": 0, "total": len(clips), "confidence": "none",
            "alternatives": [], "provider": None, "errors": errors}
