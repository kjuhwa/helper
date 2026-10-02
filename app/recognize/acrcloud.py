"""ACRCloud 어댑터 (키가 설정된 경우에만 사용)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path

import aiohttp

from .base import Match


class ACRCloudRecognizer:
    name = "acrcloud"

    def __init__(self, host: str, key: str, secret: str) -> None:
        self.host, self.key, self.secret = host, key, secret

    @classmethod
    def from_env(cls) -> "ACRCloudRecognizer | None":
        host = os.getenv("ACRCLOUD_HOST")
        key = os.getenv("ACRCLOUD_ACCESS_KEY")
        secret = os.getenv("ACRCLOUD_ACCESS_SECRET")
        return cls(host, key, secret) if host and key and secret else None

    async def recognize(self, clip: Path) -> Match | None:
        ts = str(int(time.time()))
        to_sign = "\n".join(["POST", "/v1/identify", self.key, "audio", "1", ts])
        sig = base64.b64encode(
            hmac.new(self.secret.encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        data = clip.read_bytes()
        form = aiohttp.FormData()
        form.add_field("sample", data, filename=clip.name)
        for k, v in {"access_key": self.key, "sample_bytes": str(len(data)),
                     "timestamp": ts, "signature": sig, "data_type": "audio",
                     "signature_version": "1"}.items():
            form.add_field(k, v)
        async with aiohttp.ClientSession() as s:
            async with s.post(f"https://{self.host}/v1/identify", data=form,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                res = await r.json(content_type=None)
        music = ((res.get("metadata") or {}).get("music") or [])
        if res.get("status", {}).get("code") != 0 or not music:
            return None
        m = music[0]
        return Match(
            title=m.get("title", ""),
            artist=", ".join(a.get("name", "") for a in m.get("artists", [])),
            provider="acrcloud",
            album=(m.get("album") or {}).get("name", ""),
            release_date=m.get("release_date", ""),
            isrc=(m.get("external_ids") or {}).get("isrc", "") or "",
        )
