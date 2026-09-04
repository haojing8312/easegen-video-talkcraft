"""Machine-readable standalone entrypoint for the bundled digital-human adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Optional

from media_runtime import wait_for_valid_media


RESULT_PREFIX = "EASEGEN_RESULT_JSON="


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a lip-synced MP4 from one audio file and one avatar video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--audio_path", default="example/audio.wav")
    parser.add_argument("--video_path", default="example/video.mp4")
    parser.add_argument("--output", help="Optional final MP4 path")
    parser.add_argument("--work-id", help="Stable task id; generated when omitted")
    parser.add_argument("--gpu", type=int, help="CUDA device index exposed to the runtime")
    parser.add_argument("--warmup-seconds", type=float, default=float(os.getenv("EASEGEN_DH_WARMUP_SECONDS", "30")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("EASEGEN_DH_RESULT_TIMEOUT", "1800")))
    parser.add_argument("--chunk-seconds", type=float, default=0,
                        help="Split long narration into short jobs while reusing one loaded model; 2.0 avoids the native 50-frame queue limit")
    parser.add_argument("--check", action="store_true", help="Validate runtime imports only")
    return parser.parse_args()


def emit(payload: dict, *, stream=sys.stdout) -> None:
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False), file=stream, flush=True)


def require_input(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def safe_work_id(value: Optional[str]) -> str:
    work_id = value or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", work_id):
        raise ValueError("work-id may contain only letters, digits, underscores, and hyphens")
    return work_id


def publish_output(source: Path, requested_output: Optional[str]) -> Path:
    if not requested_output:
        return source
    destination = Path(requested_output).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError(f"output must be an MP4: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source == destination:
        return source
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def run_command(command: list[str], *, timeout: float) -> None:
    result = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace",
                            timeout=timeout, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout or "no output")[-4000:]
        raise RuntimeError(f"command failed ({result.returncode}): {detail}")


def media_duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                            text=True, capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError(f"cannot probe narration duration: {(result.stderr or '').strip()}")
    return float(result.stdout.strip())


def split_audio(audio: Path, directory: Path, chunk_seconds: float) -> list[Path]:
    duration = media_duration(audio)
    chunks: list[Path] = []
    start = 0.0
    index = 0
    while start < duration - 0.001:
        length = min(chunk_seconds, duration - start)
        chunk = directory / f"audio-{index:03d}.wav"
        run_command(["ffmpeg", "-loglevel", "warning", "-y", "-ss", f"{start:.6f}",
                     "-t", f"{length:.6f}", "-i", str(audio), "-ac", "1", "-ar", "16000",
                     "-c:a", "pcm_s16le", str(chunk)], timeout=120)
        chunks.append(chunk)
        start += length
        index += 1
    return chunks


def concat_chunks(parts: list[Path], audio: Path, output: Path, directory: Path, timeout: float) -> Path:
    manifest = directory / "concat.txt"
    manifest.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    silent = directory / "stitched.mp4"
    run_command(["ffmpeg", "-loglevel", "warning", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(manifest), "-an", "-c:v", "copy", str(silent)], timeout=timeout)
    from media_runtime import mux_audio_video
    return mux_audio_video(audio, silent, output, timeout=timeout)


def run_chunked(task, audio: Path, video: Path, work_id: str, output: Path,
                output_dir: Path, chunk_seconds: float, timeout: float) -> Path:
    if chunk_seconds <= 0 or chunk_seconds > 2.0:
        raise ValueError("chunk-seconds must be in (0, 2.0]; the native queue is only safe below 50 frames")
    scratch = Path(tempfile.mkdtemp(prefix=f"easegen-dh-{work_id}-"))
    try:
        chunks = split_audio(audio, scratch, chunk_seconds)
        generated: list[Path] = []
        for index, chunk in enumerate(chunks):
            chunk_id = f"{work_id}-c{index:03d}"
            task.task_dic[chunk_id] = str(Path("result") / chunk_id)
            task.work(str(chunk), str(video), chunk_id, 0, 0, 0, 1)
            task_result = task.task_dic.get(chunk_id, ())
            status_text = str(task_result[0]).lower() if isinstance(task_result, (tuple, list)) and task_result else ""
            if "error" in status_text or "fail" in status_text:
                detail = task_result[3] if len(task_result) > 3 and task_result[3] else "native inference failed"
                raise RuntimeError(f"chunk {index + 1}/{len(chunks)} failed: {detail}")
            part = wait_for_valid_media([output_dir / f"{chunk_id}.mp4"], timeout=timeout)
            generated.append(part)
            emit({"status": "progress", "work_id": work_id, "chunk": index + 1, "chunks": len(chunks)})
        return concat_chunks(generated, audio, output, scratch, timeout)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    args = get_args()
    started = time.monotonic()
    try:
        if args.gpu is not None:
            if args.gpu < 0:
                raise ValueError("gpu must be a non-negative device index")
            os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
        os.environ.setdefault(
            "PYTORCH_CUDA_ALLOC_CONF",
            "expandable_segments:True,garbage_collection_threshold:0.8,max_split_size_mb:100",
        )

        import trans_dh_service

        if args.check:
            emit({"status": "ok", "mode": "check", "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES")})
            return 0

        audio = require_input(args.audio_path, "narration audio")
        video = require_input(args.video_path, "avatar video")
        work_id = safe_work_id(args.work_id)
        if args.warmup_seconds < 0 or args.timeout <= 0:
            raise ValueError("warmup-seconds must be non-negative and timeout must be positive")

        chunk_root: Optional[Path] = None
        if args.chunk_seconds:
            chunk_root = Path(tempfile.mkdtemp(prefix="easegen-dh-output-"))
            os.environ["EASEGEN_DH_LOCAL_OUTPUT_DIR"] = str(chunk_root)
        elif args.output:
            os.environ["EASEGEN_DH_LOCAL_OUTPUT"] = str(Path(args.output).expanduser().resolve())
        sys.argv = [sys.argv[0]]
        task = trans_dh_service.TransDhTask()
        if args.warmup_seconds:
            time.sleep(args.warmup_seconds)
        if args.chunk_seconds:
            # The writer process inherits this directory at spawn. Reuse the loaded native workers
            # for every short task, then stitch video and restore the untouched full narration.
            assert chunk_root is not None
            os.environ["EASEGEN_DH_LOCAL_OUTPUT_DIR"] = str(chunk_root)
            output = Path(args.output).expanduser().resolve() if args.output else Path("result") / f"{work_id}-r.mp4"
            generated = run_chunked(task, audio, video, work_id, output, chunk_root,
                                    args.chunk_seconds, args.timeout)
            emit({"status": "ok", "work_id": work_id, "output": str(generated), "chunk_seconds": args.chunk_seconds,
                  "elapsed_seconds": round(time.monotonic() - started, 3)})
            shutil.rmtree(chunk_root, ignore_errors=True)
            return 0

        task.task_dic[work_id] = str(Path("result") / work_id)
        task.work(str(audio), str(video), work_id, 0, 0, 0, 1)

        task_result = task.task_dic.get(work_id, ())
        status_text = str(task_result[0]).lower() if isinstance(task_result, (tuple, list)) and task_result else ""
        if "error" in status_text or "fail" in status_text:
            detail = task_result[3] if len(task_result) > 3 and task_result[3] else "native inference failed"
            raise RuntimeError(detail)
        reported = task_result[2] if isinstance(task_result, (tuple, list)) and len(task_result) > 2 else None
        candidates = [item for item in (reported, Path("result") / f"{work_id}-r.mp4", Path("result") / f"{work_id}.mp4") if item]
        generated = wait_for_valid_media(candidates, timeout=args.timeout)
        output = publish_output(generated, args.output)
        emit({"status": "ok", "work_id": work_id, "output": str(output),
              "elapsed_seconds": round(time.monotonic() - started, 3)})
        return 0
    except Exception as exc:
        emit({"status": "error", "error_type": type(exc).__name__, "message": str(exc),
              "elapsed_seconds": round(time.monotonic() - started, 3)}, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
