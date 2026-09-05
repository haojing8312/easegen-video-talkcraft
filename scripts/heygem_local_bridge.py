#!/usr/bin/env python3
"""Run the Skill-owned standalone adapter against an external model engine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


RESULT_PREFIX = "EASEGEN_RESULT_JSON="
STANDALONE_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "easegen-digitalhuman-v2-standalone"


class BridgeError(RuntimeError):
    pass


def is_windows() -> bool:
    return os.name == "nt"


def require_path(value: str, label: str, *, directory: bool = False) -> Path:
    path = Path(value).expanduser().resolve() if value else None
    valid = path and (path.is_dir() if directory else path.is_file())
    if not valid:
        raise BridgeError(f"{label} does not exist: {value or '<not provided>'}")
    return path


def build_command(args: argparse.Namespace) -> list[str]:
    engine = require_path(args.engine_root, "digital-human engine", directory=True)
    launcher = STANDALONE_ROOT / "run-local.sh"
    if not launcher.is_file():
        raise BridgeError(f"Skill standalone launcher does not exist: {launcher}")

    if is_windows():
        raise BridgeError("heygem-local is Linux-only; use heygem-win-onnx on Windows (WSL is not used)")
    command = ["bash", str(launcher), "--engine-root", str(engine)]
    convert = lambda path: str(path)

    if args.check:
        return command + ["--check", "--gpu", str(args.gpu), "--warmup-seconds", "0"]

    audio = require_path(args.audio, "narration audio")
    avatar = require_path(args.avatar, "avatar video")
    if not args.output:
        raise BridgeError("--output is required")
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".mp4":
        raise BridgeError("--output must end in .mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    return command + [
        "--audio_path", convert(audio),
        "--video_path", convert(avatar),
        "--output", convert(output),
        "--gpu", str(args.gpu),
        "--timeout", str(args.timeout),
        "--warmup-seconds", str(args.warmup_seconds),
    ] + (["--chunk-seconds", str(args.chunk_seconds)] if args.chunk_seconds else [])


def parse_runtime_result(output: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.replace("\x00", "").splitlines():
        if RESULT_PREFIX not in line:
            continue
        raw = line.split(RESULT_PREFIX, 1)[1].strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    if not payloads:
        raise BridgeError("runtime did not return the EASEGEN_RESULT_JSON contract")
    return payloads[-1]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--engine-root", "--runtime-root", dest="engine_root",
                      default=os.getenv("EASEGEN_DIGITALHUMAN_ENGINE_ROOT",
                                        os.getenv("EASEGEN_DIGITALHUMAN_ROOT", "")),
                      help="External engine/model directory; --runtime-root is a compatibility alias")
    root.add_argument("--audio", default="")
    root.add_argument("--avatar", default="")
    root.add_argument("--output", default="")
    root.add_argument("--gpu", type=int, default=0)
    root.add_argument("--timeout", type=float, default=1800)
    root.add_argument("--warmup-seconds", type=float, default=30)
    root.add_argument("--chunk-seconds", type=float, default=0,
                      help="Use the standalone adapter's long-audio queue workaround (recommended: 2.0)")
    root.add_argument("--check", action="store_true")
    root.add_argument("--dry-run", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        command = build_command(args)
        if args.dry_run:
            print(json.dumps({"success": True, "command": command}, ensure_ascii=False))
            return 0
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(60, int(args.timeout) + int(args.warmup_seconds) + 120),
            shell=False,
        )
        runtime_result = parse_runtime_result((result.stdout or "") + "\n" + (result.stderr or ""))
        if result.returncode or runtime_result.get("status") != "ok":
            raise BridgeError(runtime_result.get("message") or f"runtime exited with {result.returncode}")
        if not args.check:
            output = Path(args.output).expanduser().resolve()
            if not output.is_file() or output.stat().st_size <= 0:
                raise BridgeError(f"runtime output does not exist or is empty: {output}")
        print(json.dumps({
            "success": True,
            "backend": "heygem-local",
            "output": str(Path(args.output).expanduser().resolve()) if args.output else "",
            "runtime": runtime_result,
        }, ensure_ascii=False))
        return 0
    except (BridgeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"success": False, "type": type(exc).__name__, "error": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
