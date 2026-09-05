from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "heygem_win_onnx_bridge.py"
SPEC = importlib.util.spec_from_file_location("easegen_video_talkcraft_heygem_win_bridge", SCRIPT)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "heygem-win"
    python = runtime / "py39" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    return runtime


def _args(tmp_path: Path, **changes) -> argparse.Namespace:
    runtime = _runtime(tmp_path)
    audio = tmp_path / "voice.wav"
    avatar = tmp_path / "avatar.mp4"
    audio.write_bytes(b"wav")
    avatar.write_bytes(b"mp4")
    args = bridge.parser().parse_args([
        "--runtime-root", str(runtime), "--audio", str(audio),
        "--avatar", str(avatar), "--output", str(tmp_path / "host.mp4"),
    ])
    for name, value in changes.items():
        setattr(args, name, value)
    return args


def test_build_check_command_uses_bundled_python_without_wsl(tmp_path: Path):
    runtime = _runtime(tmp_path)
    args = bridge.parser().parse_args(["--runtime-root", str(runtime), "--gpu", "1", "--check"])

    command = bridge.build_command(args)

    assert command[0] == str(runtime / "py39" / "python.exe")
    assert "wsl" not in " ".join(command).lower()
    assert command[-1] == "--check"
    assert command[1:3] == ["-B", "-s"]
    assert "--audio" not in command
    assert "--avatar" not in command
    assert "--output" not in command
    assert command[command.index("--gpu") + 1] == "1"


def test_build_render_command_defaults_to_low_vram_profile(tmp_path: Path):
    args = _args(tmp_path)

    command = bridge.build_command(args)

    assert command[command.index("--batch-size") + 1] == "1"
    assert "--face-enhancement" not in command
    assert "wsl" not in " ".join(command).lower()
    assert command[command.index("--startup-timeout") + 1] == "120"
    assert command[command.index("--face-id") + 1] == "0"
    assert not {"--steps", "--low", "--multi-face", "--warmup-seconds"} & set(command)


def test_workspace_substitution_and_supported_options(tmp_path: Path):
    args = _args(tmp_path, batch_size=2, startup_timeout=45.0, face_id=3,
                 face_enhancement=True, overwrite=True)
    workspace = tmp_path / "job"
    command = bridge.build_command(args, workspace)
    assert command[command.index("--runtime-root") + 1] == str(workspace)
    assert command[command.index("--startup-timeout") + 1] == "45.0"
    assert command[command.index("--face-id") + 1] == "3"
    assert "--face-enhancement" in command
    assert "--overwrite" in command


def test_existing_output_requires_explicit_overwrite(tmp_path: Path):
    args = _args(tmp_path)
    output = Path(args.output)
    output.write_bytes(b"previous successful video")
    with pytest.raises(bridge.BridgeError, match="already exists"):
        bridge.build_command(args)
    assert output.read_bytes() == b"previous successful video"
    args.overwrite = True
    assert "--overwrite" in bridge.build_command(args)
    assert output.read_bytes() == b"previous successful video"


@pytest.mark.parametrize("input_name", ["audio", "avatar"])
def test_output_cannot_overwrite_input_even_when_opted_in(tmp_path: Path, input_name: str):
    args = _args(tmp_path, overwrite=True)
    source = tmp_path / (input_name + "-input.mp4")
    source.write_bytes(b"original input")
    setattr(args, input_name, str(source))
    args.output = str(source)
    with pytest.raises(bridge.BridgeError, match="overwrite an input"):
        bridge.build_command(args)
    assert source.read_bytes() == b"original input"


@pytest.mark.parametrize("relative", ["video.mp4", "nested/result/video.mp4"])
def test_output_cannot_be_inside_source_runtime(tmp_path: Path, relative: str):
    args = _args(tmp_path)
    args.output = str(Path(args.runtime_root) / relative)
    with pytest.raises(bridge.BridgeError, match="outside the original runtime"):
        bridge.build_command(args)


def test_runtime_environment_redirects_mutable_directories(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "incompatible-python-home")
    monkeypatch.setenv("PYTHONPATH", "unrelated-import-root")
    runtime, workspace = tmp_path / "runtime", tmp_path / "job"
    (runtime / "py39").mkdir(parents=True)
    env = bridge.runtime_environment(runtime, workspace)
    assert "PYTHONHOME" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONPATH"] == os.pathsep.join([str(workspace), str(workspace / "service")])
    assert all(env[name] == str(workspace / "tmp") for name in ("TEMP", "TMP", "GRADIO_TEMP_DIR"))


def test_parse_result_uses_last_machine_contract():
    text = "\n".join([
        "native logs",
        bridge.RESULT_PREFIX + json.dumps({"status": "working"}),
        bridge.RESULT_PREFIX + json.dumps({"status": "ok", "precision": "fp32"}),
    ])

    assert bridge.parse_result(text)["status"] == "ok"


def test_parse_result_rejects_unstructured_output():
    with pytest.raises(bridge.BridgeError, match="EASEGEN_WIN_ONNX_JSON"):
        bridge.parse_result("finished")


def test_parse_result_skips_malformed_and_non_object_contracts():
    text = "\n".join([
        bridge.RESULT_PREFIX + "not json",
        bridge.RESULT_PREFIX + "[]",
        "native prefix " + bridge.RESULT_PREFIX + '{"status":"ok"}\x00',
    ])
    assert bridge.parse_result(text) == {"status": "ok"}


@pytest.mark.parametrize("failure", ["timeout", "missing-contract", "nonzero"])
def test_run_native_preserves_failure_logs_and_telemetry(tmp_path: Path, monkeypatch, failure: str):
    runtime = _runtime(tmp_path)
    workspace = tmp_path / "isolated-job"
    workspace.mkdir()
    monkeypatch.setattr(bridge, "gpu_memory_used", lambda gpu: 640)
    command = ["native-python", "runner.py"]
    seen = {}

    def fake_run(actual_command, **kwargs):
        seen.update(kwargs)
        assert actual_command == command
        kwargs["stdout"].write(b"native startup diagnostics\n")
        kwargs["stdout"].flush()
        # Allow the sampler to observe a sample so failure telemetry is exercised.
        time.sleep(0.6)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(actual_command, kwargs["timeout"])
        if failure == "nonzero":
            payload = {"status": "error", "errorType": "NativeError", "message": "inference failed"}
            kwargs["stdout"].write((bridge.RESULT_PREFIX + json.dumps(payload)).encode())
            return SimpleNamespace(returncode=7)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    code, report = bridge.run_native(command, runtime, workspace, 3, 1)
    assert code == {"timeout": -1, "missing-contract": 0, "nonzero": 7}[failure]
    assert report["runtime"]["status"] == "error"
    assert seen["cwd"] == workspace
    assert seen["timeout"] == 3
    assert seen["stderr"] == subprocess.STDOUT
    telemetry = report["telemetry"]
    assert telemetry["gpuIndex"] == 1
    assert telemetry["baselineMemoryMiB"] == 640
    assert telemetry["peakSystemMemoryMiB"] == 640
    assert telemetry["sampleCount"] >= 1
    assert "whole-GPU" in telemetry["scope"]
    assert Path(telemetry["log"]).read_text().startswith("native startup diagnostics")
    assert json.loads((workspace / "report.json").read_text()) == report
    if failure == "timeout":
        assert report["runtime"]["errorType"] == "TimeoutExpired"
    elif failure == "missing-contract":
        assert "native startup diagnostics" in report["runtime"]["logTail"]
    else:
        assert report["runtime"]["errorType"] == "NativeError"


def test_main_rejects_nonzero_exit_even_with_success_contract(tmp_path: Path, monkeypatch, capsys):
    args = _args(tmp_path, check=True)
    workspace = tmp_path / "job"
    workspace.mkdir()
    report = {"runtime": {"status": "ok"}, "telemetry": {"log": str(workspace / "runner.log")}}
    monkeypatch.setattr(bridge, "os", SimpleNamespace(name="nt", getenv=os.getenv))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--runtime-root", args.runtime_root, "--check"])
    monkeypatch.setitem(sys.modules, "win_onnx_workspace", SimpleNamespace(prepare_workspace=lambda *args: workspace))
    monkeypatch.setitem(sys.modules, "win_process_job", SimpleNamespace(own_current_process_job=lambda: object()))
    monkeypatch.setattr(bridge, "run_native", lambda *args: (7, report))
    assert bridge.main() == 2
    emitted = json.loads(capsys.readouterr().err)
    assert emitted["success"] is False
    assert "7" in emitted["error"]
    assert emitted["telemetry"] == report["telemetry"]
