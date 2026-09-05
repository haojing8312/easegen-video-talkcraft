"""Fail-closed media acceptance before publishing a native job result."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess


def probe(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration:stream=codec_type,codec_name,width,height,duration",
                             "-of", "json", str(path)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60, check=True)
    return json.loads(result.stdout)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_media(output: Path, audio: Path, avatar: Path) -> dict:
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("native output is missing or empty")
    info, narration = probe(output), probe(audio)
    streams = info.get("streams", [])
    types = {s.get("codec_type") for s in streams}
    if not {"audio", "video"} <= types:
        raise RuntimeError("native output must contain both video and narration audio")
    if not any(s.get("codec_type") == "audio" for s in narration.get("streams", [])):
        raise RuntimeError("narration input has no audio stream")
    duration = float(info.get("format", {}).get("duration", 0))
    expected = float(narration.get("format", {}).get("duration", 0))
    if (not all(math.isfinite(v) and v > 0 for v in (duration, expected)) or
            abs(duration - expected) > 0.25):
        raise RuntimeError(f"output duration {duration} differs from narration {expected}")
    for stream in streams:
        if stream.get("codec_type") in {"video", "audio"} and stream.get("duration"):
            stream_duration = float(stream["duration"])
            if not math.isfinite(stream_duration) or abs(stream_duration - expected) > 0.25:
                raise RuntimeError("output stream is truncated relative to narration")
    output_hash = digest(output)
    if output_hash == digest(avatar):
        raise RuntimeError("native output is an unchanged copy of the avatar")
    result = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output),
                             "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise RuntimeError(f"native output failed full decode: {result.stderr[-2000:]}")
    return {"durationSeconds": duration, "narrationSeconds": expected,
            "streams": streams, "fullDecode": True, "sha256": output_hash}
