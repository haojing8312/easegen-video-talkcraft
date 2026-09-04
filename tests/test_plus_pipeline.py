from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


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
