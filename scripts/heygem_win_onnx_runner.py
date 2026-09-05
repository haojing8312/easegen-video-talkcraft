#!/usr/bin/env python3
"""Isolated native Windows HeyGem execution; one process lifetime per job."""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from uuid import uuid4


RESULT_PREFIX = "EASEGEN_WIN_ONNX_JSON="


def emit(payload: dict) -> None:
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=True), flush=True)


def require_file(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not value or not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {value}")
    return path


def runtime_report(root: Path) -> dict:
    if os.name != "nt":
        raise RuntimeError("heygem-win-onnx requires native Windows; WSL is not supported")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(f"the compiled runtime requires Python 3.10, got {sys.version.split()[0]}")
    require_file(str(root / "service" / "trans_dh_service.cp310-win_amd64.pyd"), "native service")
    model_dir = root / "landmark2face_wy" / "checkpoints" / "anylang"
    fp16 = model_dir / "dinet_v1_20240131_wrapped_fp16.onnx"
    model = fp16 if fp16.is_file() else require_file(str(model_dir / "dinet_v1_20240131_wrapped.onnx"), "DINet ONNX model")
    import onnxruntime as ort

    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(f"CUDAExecutionProvider is unavailable: {providers}")
    return {
        "status": "ok", "mode": "check", "checkScope": "files-and-provider-availability",
        "cudaInferenceValidated": False, "python": sys.executable,
        "pythonVersion": sys.version.split()[0], "onnxruntimeVersion": ort.__version__,
        "providers": providers, "model": str(model),
        "precision": "fp16" if model == fp16 else "fp32",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--runtime-root", required=True, help="Fresh isolated workspace, not the source bundle")
    root.add_argument("--audio", default="")
    root.add_argument("--avatar", default="")
    root.add_argument("--output", default="")
    root.add_argument("--gpu", type=int, default=0)
    root.add_argument("--batch-size", type=int, choices=(1, 2, 4), default=1)
    root.add_argument("--startup-timeout", type=float, default=120)
    root.add_argument("--face-id", type=int, default=0)
    root.add_argument("--face-enhancement", action="store_true")
    root.add_argument("--overwrite", action="store_true")
    root.add_argument("--check", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    started = time.monotonic()
    # Keep ownership alive until process termination. Never manually close it:
    # the job also contains this process, plus every ffmpeg descendant.
    from win_process_job import own_current_process_job
    global _process_job
    try:
        _process_job = own_current_process_job()
        runtime = Path(args.runtime_root).expanduser().resolve(strict=True)
        os.environ["USE_ONNX"] = "true"
        os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
        report = runtime_report(runtime)
        if args.check:
            emit(report)
            return 0
        faulthandler.enable()
        faulthandler.dump_traceback_later(90, repeat=True)
        os.chdir(runtime)
        sys.path[:0] = [str(runtime), str(runtime / "service")]
        audio = require_file(args.audio, "narration audio")
        avatar = require_file(args.avatar, "avatar video")
        output = Path(args.output).expanduser().resolve()
        if output.suffix.lower() != ".mp4" or not args.output:
            raise ValueError("output must end in .mp4")
        if output.exists() and not args.overwrite:
            raise FileExistsError(f"output already exists; use --overwrite: {output}")
        # Native TestOptions reparses sys.argv; do not leak bridge flags into it.
        sys.argv = [sys.argv[0]]
        from win_onnx_native import render_native
        from win_onnx_media import validate_media

        result = render_native(runtime, audio, avatar, batch_size=args.batch_size,
                               face_enhancement=args.face_enhancement, face_id=args.face_id,
                               startup_timeout=args.startup_timeout)
        generated = Path(result["output"]).resolve(strict=True)
        if runtime not in generated.parents:
            raise RuntimeError("native result escaped its job workspace")
        validation = validate_media(generated, audio, avatar)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
        try:
            shutil.copyfile(generated, temporary)
            # Windows rename refuses overwrite; replace is opt-in only.
            temporary.replace(output) if args.overwrite else temporary.rename(output)
        finally:
            temporary.unlink(missing_ok=True)
        emit({"status": "ok", "mode": "render", **result, "output": str(output),
              "validation": validation, "precision": report["precision"],
              "elapsedSeconds": round(time.monotonic() - started, 3)})
        return 0
    except Exception as exc:
        traceback.print_exc()
        emit({"status": "error", "errorType": type(exc).__name__, "message": str(exc),
              "elapsedSeconds": round(time.monotonic() - started, 3)})
        return 1
    finally:
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    raise SystemExit(main())
