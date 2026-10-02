"""분석 작업 실행 + 진행 상태 + 재생목록 일괄 처리."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import download, media, store, youtube_rules
from .llm import compose, research, vision
from .llm.client import LLMError
from .recognize.runner import recognize_clips

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
LEGACY_CACHE = ROOT / "cache"

STEPS = ["download", "extract", "recognize", "vision", "research", "compose", "done"]
STEP_LABELS = {
    "queued": "대기 중",
    "download": "영상 받기 (URL)",
    "extract": "오디오/프레임 추출",
    "recognize": "노래 인식 (Shazam)",
    "vision": "화면 분석 (AI)",
    "research": "웹에서 정보 보강 (AI)",
    "compose": "제목·설명·태그 생성 (AI)",
    "done": "완료",
    "error": "오류",
    "canceled": "취소됨",
}
FINISHED = {"done", "error", "canceled"}
NO_AUDIO_WARNING = "오디오로 노래를 특정하지 못했고 다른 근거도 약합니다. 곡 정보가 맞는지 꼭 확인하세요."

# Claude CLI / Shazam 과부하를 막기 위해 동시에 돌리는 분석 수 제한
_slots: asyncio.Semaphore | None = None


def slots() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(max(1, int(os.getenv("HELPER_CONCURRENCY", "1"))))
    return _slots


@dataclass
class Job:
    id: str
    url: str
    hint: str
    work: Path
    cache_key: str
    title: str = ""
    playlist: str = ""
    batch_id: str = ""
    status: str = "queued"
    error: str = ""
    result: dict | None = None
    partial: dict = field(default_factory=dict)
    started: float = field(default_factory=time.time)
    cached: bool = False
    analysis_id: str = ""
    cancel: bool = False

    def public(self, with_result: bool = True) -> dict:
        d = {
            "kind": "job",
            "id": self.id, "url": self.url, "title": self.title, "hint": self.hint,
            "batch_id": self.batch_id,
            "status": self.status, "status_label": STEP_LABELS.get(self.status, self.status),
            "error": self.error, "cached": self.cached, "analysis_id": self.analysis_id,
            "elapsed": round(time.time() - self.started, 1),
        }
        if with_result:
            d["steps"] = [{"key": s, "label": STEP_LABELS[s]} for s in STEPS]
            d["result"] = self.result
        return d


@dataclass
class Batch:
    id: str
    url: str
    title: str
    hint: str
    job_ids: list[str]
    total_in_playlist: int
    created: float = field(default_factory=time.time)

    def public(self) -> dict:
        items = [JOBS[j].public(with_result=False) for j in self.job_ids]
        counts = {s: sum(1 for i in items if i["status"] == s) for s in ("done", "error", "canceled")}
        return {
            "kind": "batch",
            "id": self.id, "url": self.url, "title": self.title, "hint": self.hint,
            "total": len(items), "total_in_playlist": self.total_in_playlist,
            "done": counts["done"], "error": counts["error"], "canceled": counts["canceled"],
            "finished": all(i["status"] in FINISHED for i in items),
            "items": items, "created": self.created,
        }


JOBS: dict[str, Job] = {}
BATCHES: dict[str, Batch] = {}


def cache_key(url: str, hint: str) -> str:
    return hashlib.sha256(f"{url.strip()}|{hint.strip()}".encode()).hexdigest()[:32]


def new_job(url: str, hint: str, *, title: str = "", playlist: str = "", batch_id: str = "") -> Job:
    jid = uuid.uuid4().hex[:12]
    url = download.normalize_video_url(url)
    job = Job(id=jid, url=url, hint=hint.strip(), work=WORK / jid,
              cache_key=cache_key(url, hint), title=title, playlist=playlist, batch_id=batch_id)
    JOBS[job.id] = job
    return job


def new_batch(url: str, hint: str, playlist: dict) -> Batch:
    bid = uuid.uuid4().hex[:12]
    batch = Batch(id=bid, url=url, title=playlist["title"], hint=hint.strip(), job_ids=[],
                  total_in_playlist=playlist["count"])
    for e in playlist["entries"]:
        job = new_job(e["url"], hint, title=e["title"], playlist=playlist["title"], batch_id=bid)
        batch.job_ids.append(job.id)
    BATCHES[bid] = batch
    return batch


def cancel_batch(batch: Batch) -> int:
    n = 0
    for jid in batch.job_ids:
        job = JOBS[jid]
        if job.status == "queued":
            job.cancel = True
            job.status = "canceled"
            n += 1
    return n


def retry_batch(batch: Batch, include_canceled: bool = False) -> list[Job]:
    """오류(선택: 취소) 난 영상을 대기 상태로 되돌린다. 실행은 호출한 쪽에서."""
    targets = {"error", "canceled"} if include_canceled else {"error"}
    reset = []
    for jid in batch.job_ids:
        job = JOBS[jid]
        if job.status in targets:
            job.status, job.error, job.cancel = "queued", "", False
            job.partial, job.started = {}, time.time()
            reset.append(job)
    return reset


async def run(job: Job, force: bool = False) -> None:
    # 보관함에 있으면 대기 없이 바로 완료
    if not force:
        saved = store.find_by_cache_key(job.cache_key)
        if saved:
            job.result, job.cached, job.status = saved["result"], True, "done"
            job.analysis_id = saved["id"]
            return
    async with slots():
        if job.cancel:
            job.status = "canceled"
            return
        job.started = time.time()
        await _analyze(job)


async def _analyze(job: Job) -> None:
    work = job.work
    try:
        job.status = "download"
        video, source = await asyncio.to_thread(download.download, job.url, work / "video")
        job.title = source.get("title") or job.title

        job.status = "extract"
        info = await asyncio.to_thread(media.probe, video)
        clips = []
        if info["has_audio"]:
            clips = await asyncio.to_thread(media.extract_audio_clips, video,
                                            work / "audio", info["duration"])
        frames = await asyncio.to_thread(media.extract_frames, video,
                                         work / "frames", info["duration"])

        job.status = "recognize"
        if clips:
            recognition = await recognize_clips(clips)
        else:
            recognition = {"match": None, "confidence": "none", "votes": 0, "total": 0,
                           "errors": ["오디오 트랙이 없거나 추출 실패"]}
        job.partial["recognition"] = recognition

        job.status = "vision"
        vis = await asyncio.to_thread(vision.analyze, frames, source, job.hint) if frames \
            else {"notes": "프레임 추출 실패"}
        job.partial["vision"] = vis

        job.status = "research"
        res = await asyncio.to_thread(research.research, recognition, vis, source, job.hint)
        job.partial["research"] = res

        job.status = "compose"
        meta = await asyncio.to_thread(compose.compose, recognition, vis, res,
                                       source, job.hint)
        if not recognition.get("match") and meta.get("song_confidence") != "high":
            meta.setdefault("warnings", []).insert(0, NO_AUDIO_WARNING)
        meta = youtube_rules.apply(meta)

        job.result = {
            "meta": meta,
            "recognition": recognition,
            "vision": vis,
            "sources": res.get("sources", []),
            "research_notes": res.get("notes", ""),
            "media": info,
            "source": source,
        }
        job.analysis_id = await asyncio.to_thread(
            store.save_new, cache_key=job.cache_key, url=job.url, hint=job.hint,
            result=job.result, playlist=job.playlist)
        job.status = "done"
    except (LLMError, download.DownloadError) as e:
        log.error("job %s error: %s", job.id, e)
        job.status, job.error = "error", str(e)
    except Exception as e:
        log.error("job %s failed\n%s", job.id, traceback.format_exc())
        job.status, job.error = "error", f"{type(e).__name__}: {e}"
    finally:
        # 결과는 보관함에 남기고 받은 영상/중간 파일은 정리
        shutil.rmtree(work, ignore_errors=True)
