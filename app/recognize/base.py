"""곡 인식 provider 공통 인터페이스."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Match:
    title: str
    artist: str
    provider: str
    album: str = ""
    release_date: str = ""
    isrc: str = ""
    url: str = ""
    extra: dict = field(default_factory=dict)

    def key(self) -> str:
        """같은 곡 판정용 키: ISRC 우선, 없으면 정규화한 제목+가수."""
        if self.isrc:
            return f"isrc:{self.isrc.upper()}"
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        return f"ta:{norm(self.title)}|{norm(self.artist)}"

    def to_dict(self) -> dict:
        return asdict(self)


class Recognizer(Protocol):
    name: str

    async def recognize(self, clip: Path) -> Match | None: ...
