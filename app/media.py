"""ffmpeg 기반 미디어 추출: 길이 조회, 오디오 클립, 프레임."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def ffmpeg_exe() -> str:
    """PATH의 ffmpeg 우선, 없으면 imageio-ffmpeg 번들 바이너리."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "ffmpeg를 찾을 수 없습니다. `pip install imageio-ffmpeg` 또는 "
            "`winget install Gyan.FFmpeg` 로 설치하세요."
        ) from e


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_exe(), "-hide_banner", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe(video: Path) -> dict:
    """길이(초)와 오디오 스트림 유무. ffprobe 없이 `ffmpeg -i` 출력 파싱."""
    out = _run(["-i", str(video)]).stderr
    m = _DURATION_RE.search(out)
    duration = 0.0
    if m:
        h, mi, s = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + float(s)
    return {"duration": duration, "has_audio": "Audio:" in out}


def clip_offsets(duration: float, count: int = 6, length: float = 20.0) -> list[float]:
    """앞 10%(인트로/MC 멘트)를 건너뛰고 균등 분포한 클립 시작점."""
    if duration <= length:
        return [0.0]
    start = duration * 0.10
    end = max(start, duration - length - 1)
    if count == 1 or end <= start:
        return [round(start, 2)]
    step = (end - start) / (count - 1)
    return [round(start + i * step, 2) for i in range(count)]


def extract_audio_clips(video: Path, out_dir: Path, duration: float,
                        count: int = 6, length: float = 20.0) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, off in enumerate(clip_offsets(duration, count, length)):
        dst = out_dir / f"clip_{i}.wav"
        r = _run(["-y", "-ss", str(off), "-t", str(length), "-i", str(video),
                  "-vn", "-ac", "1", "-ar", "16000", str(dst)])
        if r.returncode == 0 and dst.exists() and dst.stat().st_size > 1000:
            clips.append(dst)
    return clips


# 관중 함성·저음 울림을 줄이고 음량을 고르게: 라이브/직캠 재시도용
DENOISE_FILTER = "highpass=f=150,lowpass=7000,dynaudnorm"


def denoise_clip(clip: Path) -> Path | None:
    dst = clip.with_name(clip.stem + "_dn.wav")
    r = _run(["-y", "-i", str(clip), "-af", DENOISE_FILTER, "-ac", "1", "-ar", "16000", str(dst)])
    return dst if r.returncode == 0 and dst.exists() and dst.stat().st_size > 1000 else None


def extract_frames(video: Path, out_dir: Path, duration: float, count: int = 10,
                   max_side: int = 1024) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    if duration <= 0:
        offsets = [0.0]
    else:
        offsets = [duration * (i + 0.5) / count for i in range(count)]
    scale = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    for i, off in enumerate(offsets):
        dst = out_dir / f"frame_{i:02d}.jpg"
        r = _run(["-y", "-ss", f"{off:.2f}", "-i", str(video), "-frames:v", "1",
                  "-vf", scale, "-q:v", "4", str(dst)])
        if r.returncode == 0 and dst.exists():
            frames.append(dst)
    return frames
