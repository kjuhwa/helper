"""분석 결과 보관함 (SQLite)."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "helper.db"

STATUSES = ("draft", "uploaded", "hold")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id          TEXT PRIMARY KEY,
                cache_key   TEXT,
                url         TEXT NOT NULL,
                hint        TEXT NOT NULL DEFAULT '',
                title       TEXT NOT NULL DEFAULT '',
                thumbnail   TEXT NOT NULL DEFAULT '',
                song        TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'draft',
                memo        TEXT NOT NULL DEFAULT '',
                result      TEXT NOT NULL,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            )""")
        _conn.execute("CREATE INDEX IF NOT EXISTS ix_cache_key ON analyses(cache_key)")
        cols = {r[1] for r in _conn.execute("PRAGMA table_info(analyses)")}
        if "playlist" not in cols:  # 이전 버전 DB 마이그레이션
            _conn.execute("ALTER TABLE analyses ADD COLUMN playlist TEXT NOT NULL DEFAULT ''")
        _conn.commit()
    return _conn


def _song_label(result: dict) -> str:
    s = (result.get("meta") or {}).get("song") or {}
    title = s.get("title_en") or s.get("title_ko") or ""
    artist = s.get("artist_en") or s.get("artist_ko") or ""
    return f"{artist} - {title}" if artist and title else title or artist


_YT_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})")


def youtube_thumb(url: str) -> str:
    m = _YT_ID.search(url or "")
    return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg" if m else ""


def _row(r: sqlite3.Row, full: bool) -> dict:
    d = dict(r)
    d["thumbnail"] = d["thumbnail"] or youtube_thumb(d["url"])
    if full:
        d["result"] = json.loads(d["result"])
    else:
        d.pop("result")
    return d


def save_new(*, cache_key: str, url: str, hint: str, result: dict, playlist: str = "") -> str:
    src = result.get("source") or {}
    aid = uuid.uuid4().hex[:12]
    now = time.time()
    with _lock:
        conn().execute(
            "INSERT INTO analyses (id, cache_key, url, hint, title, thumbnail, song, playlist,"
            " result, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (aid, cache_key, url, hint, src.get("title") or url, src.get("thumbnail") or "",
             _song_label(result), playlist, json.dumps(result, ensure_ascii=False), now, now))
        conn().commit()
    return aid


def find_by_cache_key(key: str) -> dict | None:
    r = conn().execute("SELECT * FROM analyses WHERE cache_key=? ORDER BY created_at DESC LIMIT 1",
                       (key,)).fetchone()
    return _row(r, True) if r else None


def get(aid: str) -> dict | None:
    r = conn().execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
    return _row(r, True) if r else None


def list_(q: str = "", status: str = "") -> list[dict]:
    sql, args = "SELECT * FROM analyses WHERE 1=1", []
    if status:
        sql += " AND status=?"
        args.append(status)
    if q:
        like = f"%{q}%"
        sql += (" AND (title LIKE ? OR song LIKE ? OR hint LIKE ? OR memo LIKE ? OR url LIKE ?"
                " OR playlist LIKE ?)")
        args += [like] * 6
    sql += " ORDER BY created_at DESC"
    return [_row(r, False) for r in conn().execute(sql, args).fetchall()]


EDITABLE_META = ("title_candidates", "description", "tags", "hashtags", "category")


def update(aid: str, *, meta: dict | None = None, status: str | None = None,
           memo: str | None = None) -> dict | None:
    with _lock:
        cur = get(aid)
        if not cur:
            return None
        result = cur["result"]
        if meta:
            m = result.setdefault("meta", {})
            # AI가 처음 만든 원본은 한 번만 따로 보관
            result.setdefault("original_meta", {k: m.get(k) for k in EDITABLE_META})
            for k in EDITABLE_META:
                if k in meta:
                    m[k] = meta[k]
            if "selected_title" in meta:
                m["selected_title"] = meta["selected_title"]
        fields = {"result": json.dumps(result, ensure_ascii=False), "updated_at": time.time()}
        if status is not None:
            if status not in STATUSES:
                raise ValueError(f"잘못된 상태: {status}")
            fields["status"] = status
        if memo is not None:
            fields["memo"] = memo
        sets = ", ".join(f"{k}=?" for k in fields)
        conn().execute(f"UPDATE analyses SET {sets} WHERE id=?", (*fields.values(), aid))
        conn().commit()
    return get(aid)


def delete(aid: str) -> bool:
    with _lock:
        n = conn().execute("DELETE FROM analyses WHERE id=?", (aid,)).rowcount
        conn().commit()
    return n > 0


def import_legacy_cache(cache_dir: Path) -> int:
    """예전 cache/*.json 결과를 보관함으로 옮긴다 (한 번만)."""
    if not cache_dir.exists():
        return 0
    n = 0
    for p in cache_dir.glob("*.json"):
        key = p.stem
        if find_by_cache_key(key):
            continue
        try:
            result = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        src = result.get("source") or {}
        save_new(cache_key=key, url=src.get("webpage_url") or "", hint="", result=result)
        n += 1
    return n
