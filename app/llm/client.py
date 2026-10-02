"""로컬 Claude Code CLI(`claude -p`) 호출 래퍼.

API 키 없이 이 PC에 로그인된 Claude 계정으로 동작한다.
사용자의 CLAUDE.md/설정/MCP 커넥터가 섞이지 않도록 격리 옵션을 항상 붙인다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class LLMError(RuntimeError):
    pass


def model() -> str:
    return os.getenv("HELPER_MODEL", "opus")


def claude_exe() -> str:
    exe = os.getenv("CLAUDE_CLI") or shutil.which("claude")
    if not exe:
        raise LLMError("Claude Code CLI(`claude`)를 찾을 수 없습니다. "
                       "Claude Code를 설치하고 `claude` 로 한 번 로그인하세요.")
    return exe


def run(prompt: str, *, system: str, schema: dict | None = None,
        tools: list[str] | None = None, effort: str = "medium",
        cwd: Path | None = None, timeout: int = 900) -> dict | str:
    """claude -p 실행. schema가 있으면 structured_output(dict), 없으면 결과 텍스트."""
    tools = tools or []
    args = [
        claude_exe(), "-p",
        "--output-format", "json",
        "--model", model(),
        "--effort", effort,
        "--no-session-persistence",
        "--strict-mcp-config",          # claude.ai 커넥터 등 MCP 비활성화
        "--setting-sources", "",        # 사용자/프로젝트 설정·CLAUDE.md 미적용
        "--system-prompt", system,
        "--tools", ",".join(tools),     # "" 이면 도구 없음
    ]
    if tools:
        args += ["--allowedTools", ",".join(tools)]
    if cwd:
        args += ["--add-dir", str(cwd)]
    if schema:
        args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    try:
        proc = subprocess.run(args, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"Claude CLI 응답 시간 초과 ({timeout}s)") from e
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        msg = (proc.stderr or proc.stdout).strip()[:500]
        raise LLMError(f"Claude CLI 실행 실패 (exit {proc.returncode}): {msg}") from e
    if out.get("is_error") or out.get("subtype") != "success":
        raise LLMError(f"Claude CLI 오류: {out.get('result') or out.get('subtype')}")
    if schema:
        so = out.get("structured_output")
        if not isinstance(so, dict):
            raise LLMError(f"구조화 출력이 없습니다: {str(out.get('result'))[:200]}")
        return so
    return out.get("result") or ""
