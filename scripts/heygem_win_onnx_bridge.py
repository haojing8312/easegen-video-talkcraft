#!/usr/bin/env python3
"""Launch a user-supplied HeyGem Windows ONNX bundle without WSL."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


RESULT_PREFIX = "EASEGEN_WIN_ONNX_JSON="
RUNNER = Path(__file__).with_name("heygem_win_onnx_runner.py")


class BridgeError(RuntimeError):
    pass


def require_path(value: str, label: str, *, directory: bool = False) -> Path:
    path = Path(value).expanduser().resolve() if value else None
    if not path or not (path.is_dir() if directory else path.is_file()):
        raise BridgeError(f"{label} does not exist: {value or '<not provided>'}")
    return path


def build_command(args: argparse.Namespace, workspace: Path | None = None) -> list[str]:
    runtime = require_path(args.runtime_root, "HeyGem Windows ONNX runtime", directory=True)
    python = require_path(args.runtime_python or str(runtime / "py39" / "python.exe"), "HeyGem Python")
    command = [str(python), "-B", "-s", str(RUNNER), "--runtime-root", str(runtime if args.check else workspace or runtime),
               "--gpu", str(args.gpu), "--batch-size", str(args.batch_size),
               "--startup-timeout", str(args.startup_timeout), "--face-id", str(args.face_id)]
    if args.check:
        return command + ["--check"]
    audio = require_path(args.audio, "narration audio")
    avatar = require_path(args.avatar, "avatar video")
    output = Path(args.output).expanduser().resolve()
    if not args.output or output.suffix.lower() != ".mp4":
        raise BridgeError("--output must end in .mp4")
    if output == audio or output == avatar:
        raise BridgeError("output cannot overwrite an input")
    if runtime == output.parent or runtime in output.parents:
        raise BridgeError("output must be outside the original runtime")
    if output.exists() and not args.overwrite:
        raise BridgeError(f"output already exists; use --overwrite: {output}")
    command += ["--audio", str(audio), "--avatar", str(avatar), "--output", str(output)]
    if args.face_enhancement:
        command.append("--face-enhancement")
    if args.overwrite:
        command.append("--overwrite")
    return command


def runtime_environment(runtime: Path, workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    python_root = runtime / "py39"
    additions = [python_root, python_root / "Scripts", python_root / "ffmpeg" / "bin",
                 python_root / "Lib" / "site-packages" / "torch" / "lib", python_root / "Library" / "bin"]
    env["PATH"] = os.pathsep.join(str(path) for path in additions if path.exists()) + os.pathsep + env.get("PATH", "")
    env.update({"USE_ONNX": "true", "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                "GRADIO_TEMP_DIR": str(workspace / "tmp"), "TEMP": str(workspace / "tmp"),
                "TMP": str(workspace / "tmp"), "XFORMERS_FORCE_DISABLE_TRITON": "1"})
    # Do not set expandable_segments: that CUDA allocator feature is unsupported
    # by this bundle on Windows and does not constrain ONNX Runtime arenas.
    env.pop("PYTHONHOME", None)
    env["PYTHONPATH"] = os.pathsep.join([str(workspace), str(workspace / "service")])
    return env


def parse_result(value: str) -> dict[str, Any]:
    payloads = []
    for line in value.replace("\x00", "").splitlines():
        if RESULT_PREFIX not in line:
            continue
        try:
            payload = json.loads(line.split(RESULT_PREFIX, 1)[1].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    if not payloads:
        raise BridgeError("runtime did not return the EASEGEN_WIN_ONNX_JSON contract")
    return payloads[-1]


def gpu_memory_used(gpu: int) -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--id={gpu}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, capture_output=True, timeout=5, check=False,
        )
        return int(result.stdout.strip().splitlines()[0]) if result.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def run_native(command: list[str], runtime: Path, workspace: Path,
               timeout: float, gpu: int) -> tuple[int, dict[str, Any]]:
    stop = threading.Event()
    samples: list[int] = []
    baseline = gpu_memory_used(gpu)

    def sample() -> None:
        while not stop.wait(0.5):
            used = gpu_memory_used(gpu)
            if used is not None:
                samples.append(used)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    started = time.monotonic()
    log_path = workspace / "runner.log"
    error = None
    code = -1
    try:
        with log_path.open("wb") as log:
            process = subprocess.run(command, cwd=workspace, env=runtime_environment(runtime, workspace),
                                     stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            code = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        error = {"status": "error", "errorType": type(exc).__name__, "message": str(exc)}
    finally:
        stop.set()
        thread.join(timeout=6)
    with log_path.open("rb") as log:
        log.seek(max(0, log_path.stat().st_size - 65536))
        tail = log.read().decode("utf-8", errors="replace")
    try:
        payload = error or parse_result(tail)
    except BridgeError as exc:
        payload = {"status": "error", "message": str(exc), "logTail": tail[-4000:]}
    report = {
        "runtime": payload,
        "telemetry": {
            "gpuIndex": gpu, "scope": "whole-GPU sampled usage, not exclusive process allocation",
            "baselineMemoryMiB": baseline,
            "peakSystemMemoryMiB": max(samples) if samples else baseline,
            "peakIncreaseMiB": max(0, max(samples) - baseline) if samples and baseline is not None else None,
            "sampleCount": len(samples), "elapsedSeconds": round(time.monotonic() - started, 3),
            "log": str(log_path), "workspace": str(workspace),
        },
    }
    (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return code, report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--runtime-root", default=os.getenv("EASEGEN_HEYGEM_WIN_ONNX_ROOT", ""))
    root.add_argument("--runtime-python", default="")
    root.add_argument("--audio", default="")
    root.add_argument("--avatar", default="")
    root.add_argument("--output", default="")
    root.add_argument("--gpu", type=int, default=0)
    root.add_argument("--batch-size", type=int, choices=(1, 2, 4), default=1)
    root.add_argument("--startup-timeout", type=float, default=120)
    root.add_argument("--face-id", type=int, default=0)
    root.add_argument("--face-enhancement", action="store_true")
    root.add_argument("--overwrite", action="store_true")
    root.add_argument("--timeout", type=float, default=1800)
    root.add_argument("--check", action="store_true")
    root.add_argument("--dry-run", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    report: dict[str, Any] = {}
    try:
        if os.name != "nt":
            raise BridgeError("heygem-win-onnx requires native Windows; WSL is not used")
        if (args.gpu < 0 or args.face_id < 0 or
                not all(math.isfinite(v) and v > 0 for v in (args.timeout, args.startup_timeout))):
            raise BridgeError("gpu/face-id must be non-negative and timeouts positive")
        runtime = require_path(args.runtime_root, "HeyGem Windows ONNX runtime", directory=True)
        command = build_command(args)
        if args.dry_run:
            print(json.dumps({"success": True, "command": command,
                              "note": "execution substitutes a fresh isolated workspace"}, ensure_ascii=False))
            return 0
        from win_onnx_workspace import prepare_workspace

        output_parent = (Path(tempfile.gettempdir()) / "easegen-heygem-checks" if args.check
                         else Path(args.output).expanduser().resolve().parent)
        if args.check:
            output_parent.mkdir(parents=True, exist_ok=True)
            workspace = Path(tempfile.mkdtemp(prefix="check-", dir=output_parent))
            (workspace / "tmp").mkdir()
        else:
            workspace = prepare_workspace(runtime, output_parent, args.batch_size)
        command = build_command(args, workspace)
        # An outer job also covers termination of this bridge by the pipeline.
        # The runner owns a nested job for its independent timeout path.
        from win_process_job import own_current_process_job
        global _bridge_job
        _bridge_job = own_current_process_job()
        code, report = run_native(command, runtime, workspace, args.timeout, args.gpu)
        if code or report["runtime"].get("status") != "ok":
            raise BridgeError(report["runtime"].get("message") or f"runtime exited with {code}")
        if not args.check:
            output = Path(args.output).expanduser().resolve()
            if report["runtime"].get("output") != str(output) or not output.is_file():
                raise BridgeError("runtime did not publish the requested output")
        print(json.dumps({"success": True, "backend": "heygem-win-onnx",
                          "output": str(Path(args.output).expanduser().resolve()) if args.output else "",
                          **report}, ensure_ascii=False))
        return 0
    except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"success": False, "type": type(exc).__name__, "error": str(exc), **report},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
