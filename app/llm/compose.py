"""최종 유튜브 메타데이터 구조화 생성."""
from __future__ import annotations

import json

from . import client

SYSTEM = """너는 K-pop 유튜브 채널 운영 전문가다. 수집된 근거만으로 업로드용 메타데이터를 만든다.

원칙:
- 근거(오디오 인식, 화면 텍스트, 원본 페이지 정보, 웹 리서치, 사용자 힌트)에 없는 사실을 지어내지 마라.
  불확실한 값은 빈 문자열로 두고 evidence의 confidence를 "guess"로 표시한다.
- 멤버 이름은 화면 텍스트/원본 페이지 정보/힌트로 확인된 경우에만 넣는다.
- 제목: 100자 이내, 검색에 강한 형식. 한글과 영문 병기. 예)
  "[4K] 뉴진스 하니 'Supernatural' 직캠 | NewJeans HANNI Fancam @음악중계 241005"
  직캠이 아닌 영상은 유형에 맞게 (커버, 무대, 연습 등). 후보 3개를 서로 다른 스타일로.
- 설명: 첫 2줄에 핵심(곡/아티스트/영상 유형), 이어서 크레딧(곡, 아티스트, 앨범, 발매일, 작사/작곡),
  공식 링크가 있으면 포함, 마지막 줄에 해시태그 3~5개. 한국어 위주 + 영문 한 줄 요약.
- 태그: 한글과 영문/로마자를 쌍으로 (예: 뉴진스, NewJeans, 하니, HANNI, 슈퍼내추럴, Supernatural),
  그룹명+곡명 조합, 영상 유형(직캠, fancam), 팬덤 검색어. 합계 450자 이내로 중요도 순.
- 해시태그: 5~10개, 공백 없이, 가장 중요한 3개를 앞에.
- category: 대개 "Music" (예능/비하인드는 "Entertainment")."""

_EVIDENCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["field", "value", "confidence", "basis"],
    "properties": {
        "field": {"type": "string"},
        "value": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "guess"]},
        "basis": {"type": "string"},
    },
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["song", "video_type", "title_candidates", "description", "tags",
                 "hashtags", "category", "evidence", "warnings"],
    "properties": {
        "song": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title_ko", "title_en", "artist_ko", "artist_en", "members",
                         "album", "release_date", "credits"],
            "properties": {
                "title_ko": {"type": "string"},
                "title_en": {"type": "string"},
                "artist_ko": {"type": "string"},
                "artist_en": {"type": "string"},
                "members": {"type": "array", "items": {"type": "string"}},
                "album": {"type": "string"},
                "release_date": {"type": "string"},
                "credits": {"type": "string"},
            },
        },
        "video_type": {"type": "string"},
        "title_candidates": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string", "enum": ["Music", "Entertainment", "People & Blogs"]},
        "evidence": {"type": "array", "items": _EVIDENCE},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}


def compose(recognition: dict, vision: dict, research: dict, source: dict, hint: str) -> dict:
    payload = {
        "source_page": source,
        "user_hint": hint or "",
        "audio_recognition": recognition,
        "screen_analysis": vision,
        "web_research": research,
    }
    prompt = ("다음 근거로 유튜브 업로드 메타데이터를 만들어줘. evidence에는 "
              "곡 제목/아티스트/멤버/앨범 등 주요 필드마다 근거와 신뢰도를 적어줘.\n\n"
              + json.dumps(payload, ensure_ascii=False, indent=1))
    return client.run(prompt, system=SYSTEM, schema=SCHEMA, effort="medium")
