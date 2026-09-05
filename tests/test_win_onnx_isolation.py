from __future__ import annotations

import configparser
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("win_onnx_workspace", SCRIPTS / "win_onnx_workspace.py")
assert SPEC and SPEC.loader
workspace_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace_module)


def put(root: Path, relative: str, content: bytes = b"fixture") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    put(root, "config/config.ini", b"[digital]\nbatch_size = 4\n[log]\nlog_dir = /original/log\n[register]\nenable = 1\n")
    put(root, "cy_app.cp310-win_amd64.pyd")
    put(root, "digitalhuman_interface_onnx.pyc")
    put(root, "service/worker.py", b"pass\n")
    put(root, "landmark2face_wy/checkpoints/anylang/model.onnx", b"immutable model")
    put(root, "landmark2face_wy/checkpoints/test/opt.txt", b"stale training options")
    put(root, "wenet/examples/aishell/aidata/conf/model.yaml")
    put(root, "wenet/examples/aishell/aidata/exp/conformer/model.pt")
    put(root, "service/__pycache__/worker.pyc")
    put(root, "service/cache/stale.json")
    put(root, "service/old.mp4")
    put(root, "mel/back.wav")
    put(root, "mel/model.ckpt")
    put(root, "result/stale.mp4")
    put(root, "output/stale.json")
    put(root, "py39/huge.dll")
    return root


def test_workspace_is_fresh_and_original_is_unchanged(runtime: Path, tmp_path: Path):
    before = hashes(runtime)
    first = workspace_module.prepare_workspace(runtime, tmp_path / "output", 1)
    second = workspace_module.prepare_workspace(runtime, tmp_path / "output", 2)
    assert first != second
    assert first.parent.name == ".heygem-jobs"
    assert first.parent.parent == tmp_path / "output"
    for folder, batch in ((first, "1"), (second, "2")):
        config = configparser.ConfigParser()
        config.read(folder / "config/config.ini")
        assert config["digital"]["batch_size"] == batch
        assert config["log"]["log_dir"] == "./log"
        assert config["temp"]["temp_dir"] == "./temp"
        assert config["register"]["enable"] == "0"
        assert (folder / "wenet/examples/aishell/aidata/exp/conformer/model.pt").is_file()
        assert (folder / "mel/model.ckpt").is_file()
        for name in workspace_module.MUTABLE_DIRECTORIES:
            assert (folder / name).is_dir()
            assert list((folder / name).iterdir()) == []
        for relative in ("py39", "service/cache", "service/__pycache__", "service/old.mp4", "mel/back.wav", "landmark2face_wy/checkpoints/test"):
            assert not (folder / relative).exists()
    put(first, "service/worker.py", b"changed copy")
    put(first, "result/new.mp4")
    assert hashes(runtime) == before
    assert (second / "service/worker.py").read_bytes() == b"pass\n"


def test_model_copy_fallback(runtime: Path, tmp_path: Path, monkeypatch):
    def cannot_link(*args):
        raise OSError("cross-device link")
    monkeypatch.setattr(workspace_module.os, "link", cannot_link)
    folder = workspace_module.prepare_workspace(runtime, tmp_path / "output", 1)
    relative = "landmark2face_wy/checkpoints/anylang/model.onnx"
    assert (folder / relative).read_bytes() == (runtime / relative).read_bytes()
    assert not os.path.samefile(folder / relative, runtime / relative)


def test_same_volume_models_can_be_shared_but_config_is_copied(runtime: Path, tmp_path: Path):
    folder = workspace_module.prepare_workspace(runtime, tmp_path / "output", 1)
    relative = "landmark2face_wy/checkpoints/anylang/model.onnx"
    if not os.path.samefile(folder / relative, runtime / relative):
        pytest.skip("filesystem does not support hard links")
    assert not os.path.samefile(folder / "config/config.ini", runtime / "config/config.ini")


@pytest.mark.parametrize("batch", [0, 3, 8, True, "1"])
def test_invalid_batch_rejected_without_mutating_runtime(runtime: Path, tmp_path: Path, batch):
    before = hashes(runtime)
    with pytest.raises(ValueError, match="batch_size"):
        workspace_module.prepare_workspace(runtime, tmp_path / "output", batch)
    assert hashes(runtime) == before


def test_workspace_cannot_be_nested_in_source(runtime: Path):
    with pytest.raises(ValueError, match="outside"):
        workspace_module.prepare_workspace(runtime, runtime / "output", 1)


def test_source_directory_links_are_not_followed(runtime: Path, tmp_path: Path):
    linked = runtime / "service" / "linked"
    external = tmp_path / "external"
    put(external, "secret.py")
    try:
        linked.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    folder = workspace_module.prepare_workspace(runtime, tmp_path / "output", 1)
    assert not (folder / "service/linked").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object integration")
@pytest.mark.parametrize("terminate", [False, True])
def test_job_kills_child_when_runner_exits(tmp_path: Path, terminate: bool):
    marker = tmp_path / "child-pid.txt"
    code = "\n".join([
        "import subprocess, sys, time",
        "from pathlib import Path",
        f"sys.path.insert(0, {str(SCRIPTS)!r})",
        "from win_process_job import own_current_process_job",
        "job = own_current_process_job()",
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
        f"Path({str(marker)!r}).write_text(str(child.pid))",
        "time.sleep(120)" if terminate else "time.sleep(0.1)",
    ])
    runner = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and runner.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), runner.communicate(timeout=2)
        child_pid = int(marker.read_text())
        if terminate:
            runner.terminate()
        runner.communicate(timeout=10)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, child_pid)  # SYNCHRONIZE
        if handle:
            try:
                assert kernel32.WaitForSingleObject(handle, 5000) == 0
            finally:
                kernel32.CloseHandle(handle)
        else:
            assert ctypes.get_last_error() == 87  # Child already destroyed: ERROR_INVALID_PARAMETER.
    finally:
        if runner.poll() is None:
            runner.kill()
        runner.communicate(timeout=5)
