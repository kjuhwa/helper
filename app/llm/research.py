"""웹 검색으로 곡/아티스트 정보 보강 (Claude CLI의 WebSearch/WebFetch 도구 사용)."""
from __future__ import annotations

import json

from . import client

SYSTEM = """너는 K-pop/음악 메타데이터 리서처다. 웹 검색으로 사실을 확인해 유튜브 업로드에 필요한 정보를 정리한다.
확인하지 못한 내용은 '미확인'이라고 쓰고 지어내지 마라. 근거로 쓴 페이지는 sources에 URL로 남긴다."""

PROMPT = """아래 단서로 영상 속 노래와 아티스트를 WebSearch/WebFetch로 확인하고 정리해줘.

[오디오 인식 결과]
{recognition}

[화면 분석 결과]
{vision}

[원본 페이지 정보 (영상 제목/설명/태그 등)]
{source}
[사용자 힌트] {hint}

notes에 정리할 항목:
1. 곡 제목: 한글 / 영문 / 로마자 표기
2. 아티스트: 그룹명(한글/영문), 소속사, 팬덤명
3. 영상에 나온 멤버(화면 텍스트·힌트로 확인된 경우만): 한글/영문 활동명
4. 앨범명, 발매일, 작사/작곡/편곡
5. 공식 MV 또는 음원 링크(있으면)
6. 이 곡/그룹에서 팬들이 많이 쓰는 검색어·해시태그 (한글/영문)
7. 오디오 인식 결과와 화면 단서가 서로 맞지 않으면 어느 쪽이 맞는지 판단과 근거
8. 노래를 특정할 수 없으면 가장 가능성 높은 후보들과 이유
검색은 꼭 필요한 만큼만 (최대 8회 정도)."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["notes", "sources"],
    "properties": {
        "notes": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "title"],
                "properties": {"url": {"type": "string"}, "title": {"type": "string"}},
            },
        },
    },
}


def research(recognition: dict, vision: dict, source: dict, hint: str) -> dict:
    prompt = PROMPT.format(
        recognition=json.dumps(recognition, ensure_ascii=False, indent=1),
        vision=json.dumps(vision, ensure_ascii=False, indent=1),
        source=json.dumps(source, ensure_ascii=False, indent=1), hint=hint or "(없음)",
    )
    out = client.run(prompt, system=SYSTEM, schema=SCHEMA,
                     tools=["WebSearch", "WebFetch"], effort="high")
    out["sources"] = [s for s in out.get("sources", []) if s.get("url", "").startswith("http")][:20]
    return out
