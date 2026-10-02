"""YouTube 업로드 메타데이터 헬퍼 - FastAPI 진입점.

실행: uvicorn app.main:app --reload  →  http://localhost:8000
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import download, jobs, media, store
from .llm import client as llm_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("helper")

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="YouTube Upload Helper")
_tasks: set[asyncio.Task] = set()


@app.on_event("startup")
def _startup() -> None:
    try:
        log.info("ffmpeg: %s", media.ffmpeg_exe())
    except RuntimeError as e:
        log.error("%s", e)
    moved = store.import_legacy_cache(jobs.LEGACY_CACHE)
    if moved:
        log.info("예전 캐시 %d건을 보관함으로 옮겼습니다", moved)
    try:
        log.info("claude CLI: %s (model=%s)", llm_client.claude_exe(), llm_client.model())
    except llm_client.LLMError as e:
        log.error("%s", e)


@app.get("/api/health")
def health() -> dict:
    try:
        ff = media.ffmpeg_exe()
    except RuntimeError:
        ff = None
    try:
        cli = llm_client.claude_exe()
    except llm_client.LLMError:
        cli = None
    return {"ffmpeg": ff, "claude_cli": cli, "model": llm_client.model()}


class JobIn(BaseModel):
    url: str
    hint: str = ""
    force: bool = False
    whole_playlist: bool = False  # watch?v=...&list=... 주소일 때 재생목록 전체 분석


def _spawn(job: jobs.Job, force: bool) -> None:
    task = asyncio.create_task(jobs.run(job, force=force))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@app.post("/api/jobs")
async def create_job(body: JobIn) -> dict:
    """영상 URL이면 작업 1개, 재생목록 URL이면 영상마다 작업을 만든 일괄 작업(batch)."""
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "http(s):// 로 시작하는 영상 또는 재생목록 URL을 입력하세요")
    try:
        playlist = await asyncio.to_thread(download.expand_playlist, url, body.whole_playlist)
    except download.DownloadError as e:
        raise HTTPException(400, str(e))
    if playlist is None:
        job = jobs.new_job(url, body.hint)
        _spawn(job, body.force)
        return job.public()
    batch = jobs.new_batch(url, body.hint, playlist)
    for jid in batch.job_ids:
        _spawn(jobs.JOBS[jid], body.force)
    return batch.public()


@app.get("/api/batches")
def list_batches() -> list[dict]:
    """서버가 켜진 뒤 만든 재생목록 작업 (최신순)."""
    return [b.public() for b in sorted(jobs.BATCHES.values(), key=lambda b: -b.created)]


@app.get("/api/batches/{bid}")
def get_batch(bid: str) -> dict:
    b = jobs.BATCHES.get(bid)
    if not b:
        raise HTTPException(404, "재생목록 작업을 찾을 수 없습니다")
    return b.public()


@app.post("/api/batches/{bid}/cancel")
def cancel_batch(bid: str) -> dict:
    b = jobs.BATCHES.get(bid)
    if not b:
        raise HTTPException(404, "재생목록 작업을 찾을 수 없습니다")
    return {"canceled": jobs.cancel_batch(b), "batch": b.public()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return job.public()


class AnalysisPatch(BaseModel):
    meta: dict | None = None
    status: str | None = None
    memo: str | None = None


@app.get("/api/analyses")
def list_analyses(q: str = "", status: str = "") -> list[dict]:
    return store.list_(q.strip(), status)


@app.get("/api/analyses/{aid}")
def get_analysis(aid: str) -> dict:
    a = store.get(aid)
    if not a:
        raise HTTPException(404, "보관함에 없는 항목입니다")
    return a


@app.patch("/api/analyses/{aid}")
def patch_analysis(aid: str, body: AnalysisPatch) -> dict:
    meta = body.meta
    if meta:
        # 사용자가 고친 값도 유튜브 제한에 맞춰 보정
        from . import youtube_rules
        fixed = youtube_rules.apply({**meta, "warnings": []})
        meta = {k: fixed[k] for k in meta if k in fixed}
    try:
        a = store.update(aid, meta=meta, status=body.status, memo=body.memo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not a:
        raise HTTPException(404, "보관함에 없는 항목입니다")
    return a


@app.delete("/api/analyses/{aid}")
def delete_analysis(aid: str) -> dict:
    if not store.delete(aid):
        raise HTTPException(404, "보관함에 없는 항목입니다")
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
