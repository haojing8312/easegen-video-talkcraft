from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plus_pipeline.py"
SPEC = importlib.util.spec_from_file_location("easegen_video_talkcraft_plus", SCRIPT)
assert SPEC and SPEC.loader
plus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plus)


def _args(tmp_path: Path, *, dh_backend: str = "heygem-api", tts_device: str = "cpu"):
    script = tmp_path / "source.txt"
    voice = tmp_path / "voice.wav"
    avatar = tmp_path / "avatar.mp4"
    script.write_text("第一句。第二句！", encoding="utf-8")
    voice.write_bytes(b"wav fixture")
    avatar.write_bytes(b"mp4 fixture")
    return argparse.Namespace(
        project_dir=str(tmp_path / "project"), name="CPU fixture",
        script_file=str(script), voice_reference=str(voice), avatar_video=str(avatar),
        tts_backend="indextts2-cli", tts_device=tts_device,
        indextts_command=sys.executable, indextts_python="", tts_model_dir="",
        tts_user_id="", tts_model_code="", tts_voice_type=0, tts_timeout=60,
        alignment_backend="whisper", alignment_model_dir="", skip_alignment=False,
        dh_backend=dh_backend, dh_api_base="http://127.0.0.1:17863", dh_timeout=60,
        dh_engine_root=str(tmp_path / "easegen-digitalhuman-v2") if dh_backend == "heygem-local" else "",
        dh_gpu=0, dh_warmup_seconds=30,
        dh_win_python="", dh_batch_size=1, dh_startup_timeout=120, dh_face_id=0,
        dh_face_enhancement=False,
        dh_avatar_code="demo" if dh_backend == "dh-live" else "",
        dh_live_root=str(tmp_path / "DH_live") if dh_backend == "dh-live" else "",
        dh_live_python=sys.executable if dh_backend == "dh-live" else "",
        dh_live_avatars_root=str(tmp_path / "avatars") if dh_backend == "dh-live" else "",
        dh_live_output_root=str(tmp_path / "outputs") if dh_backend == "dh-live" else "",
        dh_live_expected_commit="", easegen_python=sys.executable,
        easegen_root=str(Path(__file__).resolve().parents[1]), width=1920, height=1080, fps=30,
    )


def test_init_and_plan_cpu_heygem_profile(tmp_path: Path):
    args = _args(tmp_path)
    plus.init_project(args)
    project = Path(args.project_dir)
    manifest = plus.load_manifest(project)

    assert manifest["digitalHuman"]["backend"] == "heygem-api"
    assert manifest["digitalHuman"]["requiredDevice"] == "cuda"
    plan = plus.command_plan(project, manifest)
    assert plan["ttsCommand"][-3:] == ["--no-fp16", "--no-deepspeed", "--no-cuda-kernel"]
    assert "dh" in plan["digitalHumanCommand"]
    assert "render" in plan["digitalHumanCommand"]


def test_init_and_plan_dh_live_cpu_profile(tmp_path: Path):
    args = _args(tmp_path, dh_backend="dh-live")
    plus.init_project(args)
    project = Path(args.project_dir)
    plan = plus.command_plan(project, plus.load_manifest(project))

    assert plan["digitalHumanCommand"][1].endswith("dh_live_bridge.py")
    assert "--avatar-code" in plan["digitalHumanCommand"]
    assert "demo" in plan["digitalHumanCommand"]


def test_init_and_plan_heygem_local_profile(tmp_path: Path):
    runtime = tmp_path / "easegen-digitalhuman-v2" / "scripts"
    runtime.mkdir(parents=True)
    (runtime / "run-local.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    args = _args(tmp_path, dh_backend="heygem-local")
    plus.init_project(args)
    project = Path(args.project_dir)
    manifest = plus.load_manifest(project)
    plan = plus.command_plan(project, manifest)

    assert manifest["digitalHuman"]["requiredDevice"] == "cuda"
    assert plan["digitalHumanCommand"][1].endswith("heygem_local_bridge.py")
    assert "--engine-root" in plan["digitalHumanCommand"]
    assert "--warmup-seconds" in plan["digitalHumanCommand"]


def test_init_and_plan_heygem_win_onnx_profile(tmp_path: Path):
    runtime = tmp_path / "heygem-win-onnx"
    runtime.mkdir()
    args = _args(tmp_path, dh_backend="heygem-win-onnx")
    args.dh_engine_root = str(runtime)
    plus.init_project(args)
    project = Path(args.project_dir)
    manifest = plus.load_manifest(project)
    plan = plus.command_plan(project, manifest)

    assert manifest["digitalHuman"]["requiredDevice"] == "cuda"
    assert manifest["digitalHuman"]["batchSize"] == 1
    assert plan["digitalHumanCommand"][1].endswith("heygem_win_onnx_bridge.py")
    command = plan["digitalHumanCommand"]
    assert command[command.index("--batch-size") + 1] == "1"
    assert command[command.index("--startup-timeout") + 1] == "120"
    assert command[command.index("--face-id") + 1] == "0"
    assert "--overwrite" in command
    assert not {"--face-enhancement", "--steps", "--low", "--multi-face", "--warmup-seconds"}.intersection(command)


def test_materialize_can_reuse_inputs_already_inside_project(tmp_path: Path):
    args = _args(tmp_path)
    plus.init_project(args)
    project = Path(args.project_dir)
    manifest = plus.load_manifest(project)
    paths = plus.materialize(project, manifest)
    manifest["source"] = {
        "scriptFile": str(paths["script"]),
        "voiceReference": str(paths["voice"]),
        "avatarVideo": str(paths["avatar"]),
    }

    plus.materialize(project, manifest)
    payload = json.loads((project / "input" / "script.json").read_text(encoding="utf-8"))
    assert payload["sentences"] == ["第一句。", "第二句！"]


def test_preflight_accepts_numbered_cuda_device(tmp_path: Path):
    args = _args(tmp_path, tts_device="cuda:2")
    plus.init_project(args)
    project = Path(args.project_dir)
    report = plus.preflight(project, plus.load_manifest(project), offline=True)
    device_check = next(item for item in report["checks"] if item["name"] == "IndexTTS2 device")
    assert device_check["ok"] is True


def test_native_preflight_checks_bridge_python_with_indextts(tmp_path: Path):
    args = _args(tmp_path, dh_backend="heygem-win-onnx")
    args.easegen_python = str(tmp_path / "missing-python.exe")
    plus.init_project(args)
    project = Path(args.project_dir)

    report = plus.preflight(project, plus.load_manifest(project), offline=True)

    check = next(item for item in report["checks"] if item["name"] == "digital-human bridge Python")
    assert check["ok"] is False
    assert report["success"] is False


@pytest.mark.parametrize("backend,wrong_os", [("heygem-local", "Windows"), ("heygem-win-onnx", "Linux")])
def test_native_preflight_does_not_launch_wrong_os(tmp_path: Path, monkeypatch, backend: str, wrong_os: str):
    args = _args(tmp_path, dh_backend=backend)
    runtime = tmp_path / "engine"
    (runtime / "py39").mkdir(parents=True)
    (runtime / "py39" / "python.exe").write_bytes(b"fixture")
    args.dh_engine_root = str(runtime)
    plus.init_project(args)
    project = Path(args.project_dir)
    monkeypatch.setattr(plus.platform, "system", lambda: wrong_os)

    def unexpected_run(*args, **kwargs):
        pytest.fail("preflight launched a backend on the wrong OS")

    monkeypatch.setattr(plus, "run", unexpected_run)
    report = plus.preflight(project, plus.load_manifest(project), offline=False)

    assert report["success"] is False
    assert any(item["name"].endswith("OS") and item["ok"] is False for item in report["checks"])


def test_win_preflight_reports_launch_error(tmp_path: Path, monkeypatch):
    args = _args(tmp_path, dh_backend="heygem-win-onnx")
    runtime = tmp_path / "engine"
    (runtime / "py39").mkdir(parents=True)
    (runtime / "py39" / "python.exe").write_bytes(b"fixture")
    args.dh_engine_root = str(runtime)
    plus.init_project(args)
    project = Path(args.project_dir)
    monkeypatch.setattr(plus.platform, "system", lambda: "Windows")

    def fail_launch(*args, **kwargs):
        raise OSError("invalid executable")

    monkeypatch.setattr(plus, "run", fail_launch)
    report = plus.preflight(project, plus.load_manifest(project), offline=False)

    check = next(item for item in report["checks"] if "provider capability" in item["name"])
    assert check["ok"] is False
    assert "invalid executable" in check["detail"]


@pytest.mark.parametrize("has_audio,matching_hash", [(True, False), (False, False), (True, True)])
def test_presenter_media_contract_and_telemetry(tmp_path: Path, monkeypatch, has_audio: bool, matching_hash: bool):
    args = _args(tmp_path, dh_backend="heygem-win-onnx")
    plus.init_project(args)
    project = Path(args.project_dir)
    output = project / "presenter" / "host.mp4"
    report = {"success": True, "output": str(output), "runtime": {"batchSize": 1},
              "telemetry": {"peakIncreaseMiB": 123, "log": "job.log"}}
    monkeypatch.setattr(plus, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, json.dumps(report), ""))
    avatar = Path(args.avatar_video)

    def probe(path):
        if path == avatar:
            return {"duration": 5.0, "sha256": "template"}
        streams = [{"codec_type": "video"}]
        if has_audio:
            streams.append({"codec_type": "audio"})
        return {"duration": 5.0, "sha256": "template" if matching_hash else "generated", "streams": streams}

    monkeypatch.setattr(plus, "probe", probe)
    if not has_audio or matching_hash:
        message = "video and audio" if not has_audio else "indistinguishable"
        with pytest.raises(plus.PipelineError, match=message):
            plus.generate_presenter(project, plus.load_manifest(project), {"avatar": avatar}, {"duration": 5.0})
    else:
        result = plus.generate_presenter(project, plus.load_manifest(project), {"avatar": avatar}, {"duration": 5.0})
        assert result["job"]["telemetry"] == report["telemetry"]
        assert result["job"]["runtime"] == report["runtime"]


def test_run_decodes_chinese_subprocess_output(tmp_path: Path):
    result = plus.run([sys.executable, "-c", "print('数字人生成完成')"], cwd=tmp_path, timeout=30)

    assert result.stdout.strip() == "数字人生成完成"
