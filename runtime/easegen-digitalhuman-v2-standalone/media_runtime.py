"""Safe media finalization and validation for the standalone adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from typing import Dict, Iterable, Optional, Sequence, Union


PathValue = Union[os.PathLike, str]


class MediaRuntimeError(RuntimeError):
    pass


def run_media(command: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess:
    try:
        completed = subprocess.run(list(command), check=False, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaRuntimeError(f"cannot execute media command {command[0]}: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "no output").strip()[-4000:]
        raise MediaRuntimeError(f"media command exited with {completed.returncode}: {detail}")
    return completed


def probe_media(path: PathValue, ffprobe: str = "ffprobe") -> dict:
    media = Path(path).expanduser().resolve()
    if not media.is_file() or media.stat().st_size <= 0:
        raise MediaRuntimeError(f"media file does not exist or is empty: {media}")
    completed = run_media([
        ffprobe, "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json", str(media),
    ], timeout=60)
    try:
        payload = json.loads(completed.stdout)
        duration = float(payload.get("format", {}).get("duration") or 0)
        streams = payload.get("streams", [])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaRuntimeError(f"ffprobe returned invalid JSON for {media}") from exc
    stream_types = {stream.get("codec_type") for stream in streams}
    if duration <= 0 or not {"audio", "video"}.issubset(stream_types):
        raise MediaRuntimeError(f"output lacks valid audio, video, or duration: {media}")
    return payload


def mux_audio_video(audio_path: PathValue, silent_video_path: PathValue, output_path: PathValue,
                    *, ffmpeg: str = "ffmpeg", timeout: float = 1800) -> Path:
    audio = Path(audio_path).expanduser().resolve()
    video = Path(silent_video_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    for source, label in ((audio, "audio"), (video, "silent video")):
        if not source.is_file():
            raise MediaRuntimeError(f"missing {label}: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    run_media([
        ffmpeg, "-loglevel", "warning", "-y", "-threads", "0", "-i", str(audio), "-i", str(video),
        "-map", "1:v:0", "-map", "0:a:0", "-c:a", "aac", "-c:v", "libx264", "-preset",
        os.getenv("EASEGEN_DH_X264_PRESET", "fast"), "-crf", os.getenv("EASEGEN_DH_X264_CRF", "18"),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-shortest", str(output),
    ], timeout=timeout)
    probe_media(output)
    return output


def wait_for_valid_media(candidates: Iterable[PathValue], *, timeout: float,
                         poll_interval: float = 1.0, ffprobe: str = "ffprobe") -> Path:
    paths = [Path(item).expanduser().resolve() for item in candidates]
    deadline = time.monotonic() + timeout
    previous_sizes: Dict[Path, int] = {}
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        for path in paths:
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            size = path.stat().st_size
            if previous_sizes.get(path) != size:
                previous_sizes[path] = size
                continue
            try:
                probe_media(path, ffprobe=ffprobe)
                return path
            except MediaRuntimeError as exc:
                last_error = exc
        time.sleep(poll_interval)
    detail = f": {last_error}" if last_error else ""
    raise MediaRuntimeError(f"timed out waiting for output: {', '.join(map(str, paths))}{detail}")
