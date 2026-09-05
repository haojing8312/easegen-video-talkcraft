from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "heygem_local_bridge.py"
SPEC = importlib.util.spec_from_file_location("easegen_video_talkcraft_heygem_bridge", SCRIPT)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def test_parse_runtime_result_uses_last_machine_contract():
    output = "\n".join([
        "native startup log",
        bridge.RESULT_PREFIX + json.dumps({"status": "working"}),
        bridge.RESULT_PREFIX + json.dumps({"status": "ok", "elapsed_seconds": 12.5}),
    ])

    assert bridge.parse_runtime_result(output) == {"status": "ok", "elapsed_seconds": 12.5}


def test_parse_runtime_result_rejects_unstructured_success_text():
    with pytest.raises(bridge.BridgeError, match="EASEGEN_RESULT_JSON"):
        bridge.parse_runtime_result("finished successfully")


def test_build_check_command_never_requires_media_on_linux(tmp_path: Path, monkeypatch):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setattr(bridge, "is_windows", lambda: False)
    args = argparse.Namespace(
        engine_root=str(engine), audio="", avatar="", output="", gpu=2,
        timeout=60, warmup_seconds=30, check=True, dry_run=False,
    )

    command = bridge.build_command(args)

    assert "--check" in command
    assert command[-4:] == ["--gpu", "2", "--warmup-seconds", "0"]


def test_windows_requires_native_onnx_backend(tmp_path: Path, monkeypatch):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setattr(bridge, "is_windows", lambda: True)
    args = argparse.Namespace(
        engine_root=str(engine), audio="", avatar="", output="", gpu=0,
        timeout=60, warmup_seconds=0, chunk_seconds=0, check=True, dry_run=False,
    )

    with pytest.raises(bridge.BridgeError, match="heygem-win-onnx"):
        bridge.build_command(args)
