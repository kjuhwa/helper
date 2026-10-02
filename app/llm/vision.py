"""영상 프레임 화면 분석."""
from __future__ import annotations

import json

from pathlib import Path

from . import client

SYSTEM = """너는 유튜브 업로드용 K-pop/음악 영상 분석가다.
주어진 영상 프레임(시간순), 원본 페이지 정보(제목·설명·태그), 사용자 힌트를 보고 영상이 무엇인지 판단한다.

규칙:
- 사람의 얼굴이나 외모만으로 실제 인물이 누구인지 판정하지 마라.
  인물/멤버 이름은 화면에 보이는 텍스트(자막, 네임 캡션, 워터마크), 원본 페이지 정보, 사용자 힌트에서만 가져온다.
- 화면 텍스트는 보이는 그대로 옮겨 적는다 (오탈자 추정 보정 금지).
- 방송사·프로그램 로고(예: 음악중계 프로그램), 무대/연습실/거리공연/콘서트 같은 장소 단서를 적는다.
- 확실하지 않으면 빈 문자열/빈 배열로 두고 notes에 이유를 적는다."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["video_type", "on_screen_text", "program_or_venue", "people_from_text",
                 "song_candidates", "visual_summary", "quality_hint", "notes"],
    "properties": {
        "video_type": {
            "type": "string",
            "enum": ["fancam", "stage", "music_video", "dance_cover", "vocal_cover",
                     "practice", "busking", "concert", "behind", "other"],
        },
        "on_screen_text": {"type": "array", "items": {"type": "string"}},
        "program_or_venue": {"type": "string"},
        "people_from_text": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "source"],
                "properties": {
                    "name": {"type": "string"},
                    "source": {"type": "string", "enum": ["on_screen_text", "page_info", "hint"]},
                },
            },
        },
        "song_candidates": {"type": "array", "items": {"type": "string"}},
        "visual_summary": {"type": "string"},
        "quality_hint": {"type": "string"},
        "notes": {"type": "string"},
    },
}


def analyze(frames: list[Path], source: dict, hint: str) -> dict:
    listing = "\n".join(f"- 프레임 {i + 1}/{len(frames)}: {f.resolve()}" for i, f in enumerate(frames))
    prompt = (
        "아래 영상 프레임 이미지 파일들을 Read 도구로 모두 열어 시간순으로 보고 분석하라.\n"
        f"{listing}\n\n"
        f"원본 페이지 정보: {json.dumps(source, ensure_ascii=False)}\n사용자 힌트: {hint or '(없음)'}\n"
        "스키마에 맞춰 답하라. visual_summary/notes는 한국어로. "
        "quality_hint에는 화질 단서(세로/가로, 4K로 보이는지 등)를 적는다."
    )
    return client.run(prompt, system=SYSTEM, schema=SCHEMA, tools=["Read"],
                      effort="medium", cwd=frames[0].parent)
