"""YouTube 메타데이터 제한 검증/보정.

- 제목 최대 100자, 설명 최대 5000자, `<` `>` 사용 불가
- 태그 합계 500자 (띄어쓰기 있는 태그는 따옴표 2자 포함, 태그 사이 쉼표 포함)
- 해시태그: 너무 많으면 YouTube가 전부 무시 (공식 60개, 일부 자료는 15개) → 보수적으로 15개 상한.
  설명 위쪽 3개가 제목 위에 노출.
"""
from __future__ import annotations

import re

TITLE_MAX = 100
DESC_MAX = 5000
TAGS_MAX = 500
HASHTAG_HARD_MAX = 60
HASHTAG_RECOMMENDED = 15


def _strip_angle(s: str) -> str:
    return s.replace("<", "").replace(">", "")


def tag_cost(tag: str) -> int:
    return len(tag) + (2 if " " in tag else 0)


def tags_total(tags: list[str]) -> int:
    if not tags:
        return 0
    return sum(tag_cost(t) for t in tags) + (len(tags) - 1)


def clean_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    """중복 제거(대소문자 무시) + `<>`/쉼표 제거 + 500자 이내로 앞에서부터 채움."""
    warnings: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = _strip_angle(t).replace(",", " ").strip().lstrip("#")
        t = re.sub(r"\s+", " ", t)
        if not t or t.lower() in seen:
            continue
        if tags_total(out + [t]) > TAGS_MAX:
            warnings.append(f"태그 500자 제한으로 '{t}' 이후 태그를 제외했습니다.")
            break
        seen.add(t.lower())
        out.append(t)
    return out, warnings


def clean_hashtag(h: str) -> str:
    h = _strip_angle(h).strip().lstrip("#")
    h = re.sub(r"\s+", "", h)  # 해시태그는 공백 불가
    return f"#{h}" if h else ""


def clean_hashtags(hashtags: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    for h in hashtags:
        h = clean_hashtag(h)
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    if len(out) > HASHTAG_RECOMMENDED:
        warnings.append(f"해시태그를 {HASHTAG_RECOMMENDED}개로 줄였습니다 (60개 초과 시 전부 무시됨).")
        out = out[:HASHTAG_RECOMMENDED]
    return out, warnings


def clean_title(title: str) -> tuple[str, list[str]]:
    t = re.sub(r"\s+", " ", _strip_angle(title)).strip()
    if len(t) > TITLE_MAX:
        return t[: TITLE_MAX - 1].rstrip() + "…", [f"제목이 {TITLE_MAX}자를 넘어 잘랐습니다: {t[:30]}…"]
    return t, []


def clean_description(desc: str) -> tuple[str, list[str]]:
    d = _strip_angle(desc).strip()
    if len(d) > DESC_MAX:
        return d[: DESC_MAX - 1] + "…", [f"설명이 {DESC_MAX}자를 넘어 잘랐습니다."]
    return d, []


def apply(meta: dict) -> dict:
    """compose 결과(dict)를 제한에 맞게 보정하고 warnings에 사유를 추가."""
    warnings = list(meta.get("warnings") or [])
    titles = []
    for t in meta.get("title_candidates") or []:
        ct, w = clean_title(t)
        if ct:
            titles.append(ct)
        warnings += w
    meta["title_candidates"] = titles
    meta["description"], w = clean_description(meta.get("description") or "")
    warnings += w
    meta["tags"], w = clean_tags(meta.get("tags") or [])
    warnings += w
    meta["hashtags"], w = clean_hashtags(meta.get("hashtags") or [])
    warnings += w
    meta["tags_total_chars"] = tags_total(meta["tags"])
    meta["warnings"] = warnings
    return meta
