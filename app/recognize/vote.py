"""여러 클립 인식 결과 투표."""
from __future__ import annotations

from collections import defaultdict

from .base import Match


def vote(matches: list[Match | None], total_clips: int) -> dict:
    """같은 곡끼리 묶어 다수결. 동률이면 먼저 나온(앞쪽 클립) 곡."""
    groups: dict[str, list[Match]] = defaultdict(list)
    order: list[str] = []
    for m in matches:
        if m is None or not m.title:
            continue
        k = m.key()
        if k not in groups:
            order.append(k)
        groups[k].append(m)
    if not groups:
        return {"match": None, "votes": 0, "total": total_clips,
                "confidence": "none", "alternatives": []}
    best = max(order, key=lambda k: (len(groups[k]), -order.index(k)))
    votes = len(groups[best])
    # 대표값: 앨범/ISRC 정보가 가장 많은 것
    rep = max(groups[best], key=lambda m: bool(m.album) + bool(m.isrc) + bool(m.release_date))
    ratio = votes / max(total_clips, 1)
    confidence = "high" if votes >= 2 and ratio >= 0.5 else "medium" if votes >= 2 else "low"
    alts = [groups[k][0].to_dict() | {"votes": len(groups[k])} for k in order if k != best]
    return {"match": rep.to_dict(), "votes": votes, "total": total_clips,
            "confidence": confidence, "alternatives": alts}
