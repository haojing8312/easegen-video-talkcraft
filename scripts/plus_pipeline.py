#!/usr/bin/env python3
"""Prepare verified local TTS and digital-human inputs for easegen-video-talkcraft."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import platform
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4


class PipelineError(RuntimeError):
    pass


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(command, cwd=cwd, encoding="utf-8", errors="replace",
                            env=env, capture_output=True, timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise PipelineError(detail or f"command exited with {result.returncode}: {command[0]}")
    return result


def probe(path: Path) -> dict[str, Any]:
    result = run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate",
         "-of", "json", str(path)],
        cwd=path.parent,
        timeout=60,
    )
    payload = json.loads(result.stdout)
    duration = float(payload.get("format", {}).get("duration", 0))
    streams = payload.get("streams", [])
    if duration <= 0:
        raise PipelineError(f"media has no positive duration: {path}")
    return {
        "path": str(path.resolve()),
        "duration": duration,
        "size": int(payload.get("format", {}).get("size", path.stat().st_size)),
        "streams": streams,
        "sha256": sha256(path),
    }


def split_sentences(text: str) -> list[str]:
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    if len(lines) > 1:
        return lines
    return [part.strip() for part in re.split(r"(?<=[。！？!?])\s*", text.strip()) if part.strip()]


def parse_json_stdout(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise PipelineError(f"{label} did not return a JSON object")


def load_manifest(project: Path) -> dict[str, Any]:
    path = project / "plus-manifest.json"
    if not path.is_file():
        raise PipelineError(f"manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1:
        raise PipelineError("plus-manifest.json requires schemaVersion 1")
    return value


def source_path(manifest: dict[str, Any], key: str) -> Path:
    path = Path(manifest["source"][key]).expanduser().resolve()
    if not path.is_file():
        raise PipelineError(f"source file does not exist: {path}")
    return path


def update_stage(state_path: Path, name: str, status: str, **extra: Any) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {
        "schemaVersion": 1,
        "stages": {},
    }
    state["updatedAt"] = time.time()
    state["stages"][name] = {"status": status, "updatedAt": time.time(), **extra}
    atomic_json(state_path, state)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


@contextmanager
def media_server(project: Path, media: dict[str, Any]) -> Iterator[str]:
    bind = str(media.get("bind", "127.0.0.1"))
    port = int(media.get("port", 0))
    server = ThreadingHTTPServer((bind, port), partial(QuietHandler, directory=str(project)))
    actual_port = int(server.server_address[1])
    base = str(media.get("publicBaseUrl") or "http://127.0.0.1:{port}").format(port=actual_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base.rstrip("/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def init_project(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project_dir).resolve()
    manifest_path = project / "plus-manifest.json"
    if manifest_path.exists():
        raise PipelineError(f"manifest already exists: {manifest_path}")
    script = Path(args.script_file).resolve()
    voice = Path(args.voice_reference).resolve()
    avatar = Path(args.avatar_video).resolve()
    for path in (script, voice, avatar):
        if not path.is_file():
            raise PipelineError(f"input does not exist: {path}")
    if voice.suffix.lower() != ".wav":
        raise PipelineError("IndexTTS2 voice reference must be WAV")
    if avatar.suffix.lower() != ".mp4":
        raise PipelineError("digital-human avatar source must be MP4")
    if args.tts_timeout <= 0 or args.dh_timeout <= 0:
        raise PipelineError("runtime timeouts must be positive")
    manifest = {
        "schemaVersion": 1,
        "name": args.name or project.name,
        "source": {
            "scriptFile": str(script),
            "voiceReference": str(voice),
            "avatarVideo": str(avatar),
        },
        "tts": {
            "backend": args.tts_backend,
            "device": args.tts_device,
            "command": args.indextts_command,
            "python": str(Path(args.indextts_python).resolve()) if args.indextts_python else "",
            "modelDir": str(Path(args.tts_model_dir).resolve()) if args.tts_model_dir else "",
            "userId": args.tts_user_id,
            "modelCode": args.tts_model_code,
            "voiceType": args.tts_voice_type,
            "timeoutSeconds": args.tts_timeout,
        },
        "alignment": {
            "enabled": not args.skip_alignment,
            "backend": args.alignment_backend,
            "modelDir": str(Path(args.alignment_model_dir).resolve()) if args.alignment_model_dir else "",
        },
        "digitalHuman": {
            "backend": args.dh_backend,
            "requiredDevice": "cuda" if args.dh_backend in {"heygem-api", "heygem-local", "heygem-win-onnx"} else "cpu",
            "apiBase": args.dh_api_base.rstrip("/"),
            "timeoutSeconds": args.dh_timeout,
            "engineRoot": str(Path(args.dh_engine_root).resolve()) if args.dh_engine_root else "",
            "gpuIndex": args.dh_gpu,
            "warmupSeconds": args.dh_warmup_seconds,
            "runtimePython": str(Path(args.dh_win_python).resolve()) if args.dh_win_python else "",
            "batchSize": args.dh_batch_size,
            "startupTimeoutSeconds": args.dh_startup_timeout,
            "faceId": args.dh_face_id,
            "faceEnhancement": args.dh_face_enhancement,
            "avatarCode": args.dh_avatar_code,
            "dhLiveRoot": str(Path(args.dh_live_root).resolve()) if args.dh_live_root else "",
            "dhLivePython": str(Path(args.dh_live_python).resolve()) if args.dh_live_python else "",
            "dhLiveAvatarsRoot": str(Path(args.dh_live_avatars_root).resolve()) if args.dh_live_avatars_root else "",
            "dhLiveOutputRoot": str(Path(args.dh_live_output_root).resolve()) if args.dh_live_output_root else "",
            "dhLiveExpectedCommit": args.dh_live_expected_commit,
        },
        "media": {"bind": "127.0.0.1", "port": 0, "publicBaseUrl": ""},
        "tools": {
            "easegenPython": str(Path(args.easegen_python).resolve()),
            "easegenRoot": str(Path(args.easegen_root).resolve()),
        },
        "output": {"width": args.width, "height": args.height, "fps": args.fps},
    }
    project.mkdir(parents=True, exist_ok=True)
    atomic_json(manifest_path, manifest)
    return {"success": True, "manifest": str(manifest_path)}


def command_plan(project: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    tts = manifest["tts"]
    audio = project / "audio" / "full.wav"
    script = project / "input" / "script.txt"
    voice = project / "input" / "voice-reference.wav"
    if tts["backend"] == "indextts2-cli":
        entrypoint = [tts["python"], "-m", "indextts.cli_v2"] if tts.get("python") else [tts["command"]]
        command = entrypoint + ["synth", "--text-file", str(script), "--voice", str(voice),
                   "--output", str(audio), "--force"]
        if tts.get("device") and tts["device"] != "auto":
            command += ["--device", tts["device"]]
        if tts.get("modelDir"):
            command += ["--model-dir", tts["modelDir"]]
        if tts.get("device") == "cpu":
            command += ["--no-fp16", "--no-deepspeed", "--no-cuda-kernel"]
    else:
        python = manifest["tools"]["easegenPython"]
        command = [python, "-m", "easegen_cli.main", "--json", "--timeout",
                   str(tts["timeoutSeconds"]), "voice", "tts", "--user-id", tts["userId"],
                   "--request-id", "<generated>", "--model-code", tts["modelCode"],
                   "--voice-type", str(tts["voiceType"]), "--text", "<script>",
                   "--reference-audio", str(voice), "--out", str(audio)]
    dh = manifest["digitalHuman"]
    if dh["backend"] == "heygem-api":
        digital_human_command = [manifest["tools"]["easegenPython"], "-m", "easegen_cli.main",
            "--json", "--timeout", str(dh["timeoutSeconds"]), "dh", "render",
            "--audio-url", "<temporary-media-url>/audio/full.wav", "--video-url",
            "<temporary-media-url>/input/avatar.mp4", "--out", str(project / "presenter" / "host.mp4"), "--wait"]
    elif dh["backend"] == "heygem-local":
        engine_root = dh.get("engineRoot") or dh.get("runtimeRoot", "")
        digital_human_command = [manifest["tools"]["easegenPython"],
            str(Path(__file__).with_name("heygem_local_bridge.py")),
            "--engine-root", engine_root, "--audio", str(audio),
            "--avatar", str(project / "input" / "avatar.mp4"),
            "--output", str(project / "presenter" / "host.mp4"),
            "--gpu", str(dh["gpuIndex"]), "--timeout", str(dh["timeoutSeconds"]),
            "--warmup-seconds", str(dh["warmupSeconds"])]
    elif dh["backend"] == "heygem-win-onnx":
        engine_root = dh.get("engineRoot") or dh.get("runtimeRoot", "")
        digital_human_command = [manifest["tools"]["easegenPython"],
            str(Path(__file__).with_name("heygem_win_onnx_bridge.py")),
            "--runtime-root", engine_root, "--audio", str(audio),
            "--avatar", str(project / "input" / "avatar.mp4"),
            "--output", str(project / "presenter" / "host.mp4"),
            "--gpu", str(dh["gpuIndex"]), "--batch-size", str(dh.get("batchSize", 1)),
            "--startup-timeout", str(dh.get("startupTimeoutSeconds", 120)),
            "--face-id", str(dh.get("faceId", 0)),
            "--timeout", str(dh["timeoutSeconds"]), "--overwrite"]
        if dh.get("runtimePython"):
            digital_human_command += ["--runtime-python", dh["runtimePython"]]
        if dh.get("faceEnhancement"):
            digital_human_command.append("--face-enhancement")
    else:
        digital_human_command = [manifest["tools"]["easegenPython"],
            str(Path(__file__).with_name("dh_live_bridge.py")),
            "--easegen-root", manifest["tools"]["easegenRoot"], "--runtime-root", dh["dhLiveRoot"],
            "--runtime-python", dh["dhLivePython"], "--avatars-root", dh["dhLiveAvatarsRoot"],
            "--avatar-code", dh["avatarCode"], "--output-root", dh["dhLiveOutputRoot"],
            "--audio", str(audio), "--out", str(project / "presenter" / "host.mp4"),
            "--timeout", str(dh["timeoutSeconds"]), "--expected-commit", dh["dhLiveExpectedCommit"]]
    return {
        "stages": ["materialize", "tts", "alignment", "digital-human", "talkcraft-handoff"],
        "ttsCommand": command,
        "digitalHumanCommand": digital_human_command,
    }


def url_reachable(base: str) -> tuple[bool, str]:
    request = Request(base.rstrip("/") + "/docs", method="HEAD")
    try:
        with urlopen(request, timeout=5) as response:
            return True, f"HTTP {response.status}"
    except HTTPError as exc:
        return exc.code in {401, 403, 405}, f"HTTP {exc.code}"
    except (URLError, OSError) as exc:
        return False, str(exc)


def preflight(project: Path, manifest: dict[str, Any], offline: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for name in ("ffmpeg", "ffprobe"):
        checks.append({"name": name, "ok": shutil.which(name) is not None})
    for key in ("scriptFile", "voiceReference", "avatarVideo"):
        try:
            path = source_path(manifest, key)
            checks.append({"name": key, "ok": True, "path": str(path)})
        except PipelineError as exc:
            checks.append({"name": key, "ok": False, "detail": str(exc)})
    tts = manifest["tts"]
    if tts["backend"] == "indextts2-cli":
        executable = tts.get("python") or tts["command"]
        resolved = Path(executable).is_file() or shutil.which(executable) is not None
        checks.append({"name": "IndexTTS2 entrypoint", "ok": resolved, "detail": executable})
        device = str(tts.get("device", "auto"))
        valid_device = device in {"auto", "cpu", "mps", "xpu"} or device == "cuda" or bool(re.fullmatch(r"cuda:\d+", device))
        checks.append({"name": "IndexTTS2 device", "ok": valid_device,
                        "detail": "CPU is supported but may be substantially slower than CUDA"})
    else:
        python = Path(manifest["tools"]["easegenPython"])
        checks.append({"name": "easegen Python", "ok": python.is_file(), "path": str(python)})
        required = all(tts.get(key) not in (None, "") for key in ("userId", "modelCode", "voiceType"))
        checks.append({"name": "Easegen TTS identity", "ok": required})
    dh = manifest["digitalHuman"]
    bridge_python_ok = Path(manifest["tools"]["easegenPython"]).is_file()
    if dh["backend"] in {"heygem-local", "heygem-win-onnx", "dh-live"}:
        checks.append({"name": "digital-human bridge Python", "ok": bridge_python_ok,
                       "path": manifest["tools"]["easegenPython"]})
    if dh["backend"] == "heygem-api":
        checks.append({"name": "HeyGem execution device", "ok": dh.get("requiredDevice") == "cuda",
                       "detail": "local open-source HeyGem requires an NVIDIA GPU"})
        if not offline:
            ok, detail = url_reachable(dh["apiBase"])
            checks.append({"name": "local HeyGem API", "ok": ok, "detail": detail, "url": dh["apiBase"]})
    elif dh["backend"] == "heygem-local":
        engine_value = dh.get("engineRoot") or dh.get("runtimeRoot", "")
        engine_root = Path(engine_value or "")
        launcher = Path(__file__).resolve().parents[1] / "runtime" / "easegen-digitalhuman-v2-standalone" / "run-local.sh"
        checks.append({"name": "HeyGem external engine", "ok": bool(engine_value) and engine_root.is_dir(),
                       "path": str(engine_root)})
        checks.append({"name": "Skill standalone launcher", "ok": launcher.is_file(), "path": str(launcher)})
        checks.append({"name": "HeyGem local OS", "ok": platform.system() == "Linux",
                       "detail": "use heygem-win-onnx for native Windows; WSL is not used"})
        if not offline and platform.system() == "Linux" and bridge_python_ok and launcher.is_file() and engine_root.is_dir():
            check_command = [manifest["tools"]["easegenPython"],
                             str(Path(__file__).with_name("heygem_local_bridge.py")),
                             "--engine-root", str(engine_root), "--gpu", str(dh.get("gpuIndex", 0)), "--check"]
            try:
                response = parse_json_stdout(run(check_command, cwd=project, timeout=180), "HeyGem local check")
                checks.append({"name": "HeyGem local native check", "ok": response.get("success") is True,
                               "detail": response})
            except (PipelineError, OSError, subprocess.TimeoutExpired) as exc:
                checks.append({"name": "HeyGem local native check", "ok": False, "detail": str(exc)})
    elif dh["backend"] == "heygem-win-onnx":
        engine_value = dh.get("engineRoot") or dh.get("runtimeRoot", "")
        engine_root = Path(engine_value or "")
        runtime_python = Path(dh.get("runtimePython") or engine_root / "py39" / "python.exe")
        bridge = Path(__file__).with_name("heygem_win_onnx_bridge.py")
        runner = Path(__file__).with_name("heygem_win_onnx_runner.py")
        checks.append({"name": "HeyGem Windows ONNX OS", "ok": platform.system() == "Windows",
                       "detail": "native Windows subprocess; WSL is not used"})
        checks.append({"name": "HeyGem Windows ONNX runtime", "ok": bool(engine_value) and engine_root.is_dir(),
                       "path": str(engine_root)})
        checks.append({"name": "HeyGem bundled Python 3.10", "ok": runtime_python.is_file(),
                       "path": str(runtime_python)})
        checks.append({"name": "HeyGem Windows ONNX bridge", "ok": bridge.is_file() and runner.is_file(),
                       "path": str(bridge)})
        if not offline and platform.system() == "Windows" and bridge_python_ok and bridge.is_file() and runner.is_file() and engine_root.is_dir() and runtime_python.is_file():
            check_command = [manifest["tools"]["easegenPython"], str(bridge),
                             "--runtime-root", str(engine_root), "--runtime-python", str(runtime_python),
                             "--gpu", str(dh.get("gpuIndex", 0)), "--batch-size", str(dh.get("batchSize", 1)),
                             "--check", "--timeout", "180"]
            try:
                response = parse_json_stdout(run(check_command, cwd=project, timeout=210), "HeyGem Windows ONNX check")
                runtime = response.get("runtime", {})
                checks.append({"name": "HeyGem ONNX provider capability (not inference)",
                               "ok": response.get("success") is True and
                                     "CUDAExecutionProvider" in runtime.get("providers", []),
                               "detail": response})
            except (PipelineError, OSError, subprocess.TimeoutExpired) as exc:
                checks.append({"name": "HeyGem ONNX provider capability (not inference)", "ok": False, "detail": str(exc)})
    elif dh["backend"] == "dh-live":
        checks.append({"name": "DH_live offline synthesis OS", "ok": platform.system() == "Windows",
                       "detail": "the audited upstream offline MP4 path currently supports Windows"})
        for label, value in (("DH_live runtime", dh.get("dhLiveRoot")),
                             ("DH_live avatars", dh.get("dhLiveAvatarsRoot"))):
            path = Path(value or "")
            checks.append({"name": label, "ok": bool(value) and path.is_dir(), "path": str(path)})
        runtime_python = Path(dh.get("dhLivePython") or "")
        checks.append({"name": "DH_live Python", "ok": runtime_python.is_file(), "path": str(runtime_python)})
        runtime_root = Path(dh.get("dhLiveRoot") or "")
        demo_script = runtime_root / "demo_mini.py"
        current_weight = runtime_root / "checkpoint" / "DINet_mini" / "epoch_40_new.pth"
        checks.append({"name": "DH_live offline entrypoint", "ok": demo_script.is_file(), "path": str(demo_script)})
        checks.append({"name": "DH_live matching checkpoint", "ok": current_weight.is_file(),
                       "path": str(current_weight),
                       "detail": "must match the pinned mini 2.0 source; do not substitute an older weight"})
        adapter = Path(manifest["tools"].get("easegenRoot", "")) / "utils" / "digital_human" / "dh_live.py"
        checks.append({"name": "Easegen DH_live adapter", "ok": adapter.is_file(), "path": str(adapter)})
        avatar_code = str(dh.get("avatarCode") or "")
        assets = Path(dh.get("dhLiveAvatarsRoot") or "") / avatar_code / "assets"
        checks.append({"name": "DH_live prepared avatar", "ok": bool(avatar_code) and
                       (assets / "01.mp4").is_file() and (assets / "combined_data.json.gz").is_file(),
                       "path": str(assets)})
    else:
        checks.append({"name": "digital-human backend", "ok": False, "detail": str(dh.get("backend"))})
    return {"success": all(item["ok"] for item in checks), "offline": offline, "checks": checks}


def materialize(project: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "script": project / "input" / "script.txt",
        "voice": project / "input" / "voice-reference.wav",
        "avatar": project / "input" / "avatar.mp4",
    }
    paths["script"].parent.mkdir(parents=True, exist_ok=True)
    for source_key, target_key in (("scriptFile", "script"), ("voiceReference", "voice"), ("avatarVideo", "avatar")):
        source = source_path(manifest, source_key)
        if source != paths[target_key].resolve():
            shutil.copy2(source, paths[target_key])
    text = paths["script"].read_text(encoding="utf-8-sig").strip()
    if not text:
        raise PipelineError("narration script is empty")
    atomic_json(project / "input" / "script.json", {"sentences": split_sentences(text)})
    return paths


def generate_tts(project: Path, manifest: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    tts = manifest["tts"]
    output = project / "audio" / "full.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    plan = command_plan(project, manifest)["ttsCommand"]
    command = [str(item) for item in plan]
    if tts["backend"] == "easegen-cli":
        text = paths["script"].read_text(encoding="utf-8-sig").strip()
        command[command.index("<generated>")] = uuid4().hex
        command[command.index("<script>")] = text
    run(command, cwd=project, timeout=int(tts["timeoutSeconds"]) + 60)
    result = probe(output)
    if not any(stream.get("codec_type") == "audio" for stream in result["streams"]):
        raise PipelineError("IndexTTS2 output has no audio stream")
    return result


def align_audio(project: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    alignment = manifest["alignment"]
    if not alignment.get("enabled", True):
        return {"skipped": True}
    skill = Path(__file__).resolve().parent
    timestamps = project / "audio" / "timestamps.json"
    command = [sys.executable, str(skill / "timestamps_cpu.py"), str(project / "audio" / "full.wav"),
               str(project / "input" / "script.json"), str(timestamps), "--backend", alignment["backend"]]
    if alignment.get("modelDir"):
        command += ["--model-dir", alignment["modelDir"]]
    run(command, cwd=project, timeout=1800)
    timing = project / "remotion-input" / "timing.json"
    timing.parent.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(skill / "make_timing.py"), str(timestamps), str(timing)], cwd=project, timeout=60)
    payload = json.loads(timestamps.read_text(encoding="utf-8"))
    failed = [row["i"] for row in payload.get("sentences", []) if row.get("ok") is not True]
    if failed:
        raise PipelineError(f"alignment requires manual review for sentence indexes: {failed}")
    return {"timestamps": str(timestamps.resolve()), "timing": str(timing.resolve())}


def generate_presenter(project: Path, manifest: dict[str, Any], paths: dict[str, Path], audio: dict[str, Any]) -> dict[str, Any]:
    output = project / "presenter" / "host.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    python = manifest["tools"]["easegenPython"]
    dh = manifest["digitalHuman"]
    if dh["backend"] == "heygem-api":
        with media_server(project, manifest.get("media", {})) as base:
            audio_url = f"{base}/audio/{quote('full.wav')}"
            avatar_url = f"{base}/input/{quote('avatar.mp4')}"
            command = [python, "-m", "easegen_cli.main", "--json", "--timeout", str(dh["timeoutSeconds"]),
                       "dh", "render", "--audio-url", audio_url, "--video-url", avatar_url,
                       "--title", manifest["name"], "--dh-api-base", dh["apiBase"],
                       "--out", str(output), "--wait"]
            response = parse_json_stdout(run(command, cwd=project, timeout=int(dh["timeoutSeconds"]) + 120), "dh render")
        terminal = response.get("data", {}).get("result", {})
        if response.get("success") is not True or terminal.get("status") != 3:
            raise PipelineError(f"HeyGem did not reach terminal status 3: {response}")
    elif dh["backend"] in {"heygem-local", "heygem-win-onnx", "dh-live"}:
        command = command_plan(project, manifest)["digitalHumanCommand"]
        response = parse_json_stdout(
            run([str(item) for item in command], cwd=project, timeout=int(dh["timeoutSeconds"]) + 120),
            f"{dh['backend']} bridge",
        )
        if response.get("success") is not True:
            raise PipelineError(f"{dh['backend']} failed: {response}")
        terminal = {"status": 3, "backend": dh["backend"], "output_file": response.get("output"),
                    "runtime": response.get("runtime"), "telemetry": response.get("telemetry")}
    else:
        raise PipelineError(f"unsupported digital-human backend: {dh['backend']}")
    result = probe(output)
    avatar = probe(paths["avatar"])
    stream_types = {stream.get("codec_type") for stream in result["streams"]}
    if not {"video", "audio"}.issubset(stream_types):
        raise PipelineError(f"{dh['backend']} output must contain video and audio streams")
    if abs(result["duration"] - audio["duration"]) > 0.25:
        raise PipelineError(f"{dh['backend']} output duration differs from narration by more than 0.25 seconds")
    if result["sha256"] == avatar["sha256"]:
        raise PipelineError(f"{dh['backend']} output is indistinguishable from the avatar template")
    face_zone = output.with_name("face-zone.json")
    run([sys.executable, str(Path(__file__).with_name("face_bbox.py")), str(output), str(face_zone)],
        cwd=project, timeout=300)
    result["job"] = terminal
    result["faceZone"] = str(face_zone.resolve())
    return result


def execute(project: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    state = project / "run-state.json"
    try:
        update_stage(state, "materialize", "running")
        paths = materialize(project, manifest)
        update_stage(state, "materialize", "success")
        update_stage(state, "tts", "running")
        audio = generate_tts(project, manifest, paths)
        update_stage(state, "tts", "success", artifact=audio)
        update_stage(state, "alignment", "running")
        alignment = align_audio(project, manifest)
        update_stage(state, "alignment", "success", artifact=alignment)
        update_stage(state, "digitalHuman", "running")
        presenter = generate_presenter(project, manifest, paths, audio)
        update_stage(state, "digitalHuman", "success", artifact=presenter)
        handoff = {
            "schemaVersion": 1,
            "script": str((project / "input" / "script.json").resolve()),
            "audio": audio,
            "presenter": presenter,
            "timestamps": alignment,
            "composition": manifest["output"],
            "nextStage": "Create SHOTBOOK, Remotion composition, machine gates, and independent review",
        }
        atomic_json(project / "talkcraft-input.json", handoff)
        update_stage(state, "talkcraftHandoff", "success", artifact=str((project / "talkcraft-input.json").resolve()))
        return {"success": True, "handoff": str((project / "talkcraft-input.json").resolve())}
    except Exception as exc:
        update_stage(state, "failure", "failed", type=type(exc).__name__, message=str(exc))
        raise


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project-dir", required=True)
    init.add_argument("--name", default="")
    init.add_argument("--script-file", required=True)
    init.add_argument("--voice-reference", required=True)
    init.add_argument("--avatar-video", required=True)
    init.add_argument("--tts-backend", choices=("indextts2-cli", "easegen-cli"), default="indextts2-cli")
    init.add_argument("--tts-device", default="auto")
    init.add_argument("--indextts-command", default="indextts2")
    init.add_argument("--indextts-python", default="",
                      help="Use PYTHON -m indextts.cli_v2 instead of a console-script wrapper")
    init.add_argument("--tts-model-dir", default="")
    init.add_argument("--tts-user-id", default="")
    init.add_argument("--tts-model-code", default="")
    init.add_argument("--tts-voice-type", type=int, default=0)
    init.add_argument("--tts-timeout", type=int, default=1800)
    init.add_argument("--alignment-backend", choices=("firered", "whisper"), default="firered")
    init.add_argument("--alignment-model-dir", default="")
    init.add_argument("--skip-alignment", action="store_true")
    init.add_argument("--dh-api-base", default="http://127.0.0.1:17863")
    init.add_argument("--dh-backend", choices=("heygem-win-onnx", "heygem-local", "heygem-api", "dh-live"),
                      default="heygem-win-onnx" if platform.system() == "Windows" else "heygem-local")
    init.add_argument("--dh-timeout", type=int, default=1800)
    init.add_argument("--dh-engine-root", "--dh-runtime-root", dest="dh_engine_root", default="",
                      help="External easegen-digitalhuman-v2 engine/model directory; legacy name remains an alias")
    init.add_argument("--dh-gpu", type=int, default=0)
    init.add_argument("--dh-warmup-seconds", type=float, default=30)
    init.add_argument("--dh-win-python", default="",
                      help="Optional Python override; defaults to ENGINE_ROOT/py39/python.exe")
    init.add_argument("--dh-batch-size", type=int, choices=(1, 2, 4), default=1,
                      help="Windows ONNX inference batch; 1 minimizes peak VRAM")
    init.add_argument("--dh-startup-timeout", type=float, default=120,
                      help="Windows ONNX worker readiness deadline in seconds")
    init.add_argument("--dh-face-id", type=int, default=0)
    init.add_argument("--dh-face-enhancement", action="store_true",
                      help="Enable GFPGAN; disabled by default to reduce peak VRAM")
    init.add_argument("--dh-avatar-code", default="")
    init.add_argument("--dh-live-root", default="")
    init.add_argument("--dh-live-python", default="")
    init.add_argument("--dh-live-avatars-root", default="")
    init.add_argument("--dh-live-output-root", default="")
    init.add_argument("--dh-live-expected-commit", default="6a1ee7d3aeb310e244bc6d6ce7703e7e8cdfbef9")
    init.add_argument("--easegen-python", default=sys.executable)
    init.add_argument("--easegen-root", default=str(Path(__file__).resolve().parents[3]))
    init.add_argument("--width", type=int, default=1920)
    init.add_argument("--height", type=int, default=1080)
    init.add_argument("--fps", type=int, default=30)
    for name in ("plan", "preflight", "run"):
        command = sub.add_parser(name)
        command.add_argument("--project-dir", required=True)
        if name == "preflight":
            command.add_argument("--offline", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            result = init_project(args)
        else:
            project = Path(args.project_dir).resolve()
            manifest = load_manifest(project)
            if args.command == "plan":
                result = {"success": True, **command_plan(project, manifest)}
            elif args.command == "preflight":
                result = preflight(project, manifest, args.offline)
            else:
                report = preflight(project, manifest, False)
                if not report["success"]:
                    raise PipelineError(f"preflight failed: {report}")
                result = execute(project, manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 2
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc), "type": type(exc).__name__},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
