from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import package_avatar_runtime as package


def put(root: Path, name: str, value: bytes = b"fixture") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "original"
    put(root, "py39/python.exe")
    put(root, "py39/Lib/site-packages/example/__init__.py", b"pass\n")
    put(root, "py39/Lib/site-packages/example/LICENSE", b"Keep this license\n")
    put(root, "py39/Lib/site-packages/example/example.wav", b"PRIVATE VOICE")
    put(root, "py39/Lib/site-packages/example/private.jpg", b"PRIVATE PORTRAIT")
    put(root, "py39/Lib/site-packages/example-1.dist-info/direct_url.json", b"private-path")
    put(root, "py39/Lib/site-packages/example/.env", b"SECRET=value")
    put(root, "py39/conda-meta/history", b"private history")
    put(root, "service/trans_dh_service.cp310-win_amd64.pyd")
    put(root, "config/config.ini", b"[register]\nurl=http://private-server\nenable=1\n")
    put(root, "mel/back.wav", b"PRIVATE VOICE")
    put(root, "mel/mel_band_roformer_small.ckpt", b"model")
    put(root, "wenet/examples/aishell/aidata/exp/conformer/wenetmodel.pt", b"model")
    put(root, "result/my-avatar.mp4", b"PRIVATE VIDEO")
    put(root, "log/service.log", b"PRIVATE LOG")
    return root


def test_clean_package_preserves_source_and_required_models(source, tmp_path):
    original = {p.relative_to(source): package.digest(p) for p in source.rglob("*") if p.is_file()}
    target = tmp_path / "release"
    manifest = package.build(source, target, "test")
    names = {item["path"] for item in manifest["files"]}
    assert "engine/mel/mel_band_roformer_small.ckpt" in names
    assert "engine/wenet/examples/aishell/aidata/exp/conformer/wenetmodel.pt" in names
    assert "engine/py39/Lib/site-packages/example/LICENSE" in names
    assert "adapter/heygem_win_onnx_bridge.py" in names
    assert not any(Path(name).suffix.lower() in package.MEDIA for name in names)
    assert not any("direct_url" in name or "conda-meta" in name or name.endswith(".env") for name in names)
    config = (target / "engine/config/config.ini").read_text()
    assert "private-server" not in config
    assert "enable = 0" in config and "batch_size = 1" in config
    assert original == {p.relative_to(source): package.digest(p) for p in source.rglob("*") if p.is_file()}
    for entry in manifest["files"]:
        assert package.digest(target / entry["path"]) == entry["sha256"]


def test_refuse_existing_or_nested_target(source, tmp_path):
    with pytest.raises(ValueError):
        package.build(source, source / "release", "test")
    with pytest.raises(ValueError):
        package.build(source, source.parent, "test")
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = put(target, "keep.txt")
    with pytest.raises(FileExistsError):
        package.build(source, target, "test")
    assert sentinel.read_bytes() == b"fixture"


def test_adapter_refresh_does_not_accept_extra_files(source, tmp_path):
    target = tmp_path / "release"
    package.build(source, target, "test")
    before = package.digest(target / "manifest.json")
    put(target, "engine/extra-cache.nbi")
    with pytest.raises(ValueError, match="extra/missing"):
        package.refresh_adapters(target)
    assert package.digest(target / "manifest.json") == before


def test_adapter_refresh_preserves_model_hashes(source, tmp_path):
    target = tmp_path / "release"
    before = package.build(source, target, "test")
    package.refresh_adapters(target)
    after = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert before == after


def test_archive_hash_and_refuse_private_postbuild_content(source, tmp_path, monkeypatch):
    target = tmp_path / "release"
    package.build(source, target, "test")
    put(target, "output/private.mp4", b"private")
    monkeypatch.setattr(sys, "argv", ["package", "--source", str(source), "--output", str(target),
                                    "--version", "test", "--redistribution-confirmed", "--archive-only"])
    with pytest.raises(ValueError, match="inventory changed"):
        package.main()
    assert not target.with_suffix(".zip").exists()


def test_archive_is_extractable_with_checksums(source, tmp_path, monkeypatch):
    target = tmp_path / "release-1.0.0"
    package.build(source, target, "test")
    monkeypatch.setattr(sys, "argv", ["package", "--source", str(source), "--output", str(target),
                                    "--version", "test", "--redistribution-confirmed", "--archive-only"])
    package.main()
    archive = target.with_name(target.name + ".zip")
    with zipfile.ZipFile(archive) as stream:
        assert stream.testzip() is None
        assert "release-1.0.0/manifest.json" in stream.namelist()
        assert "release-1.0.0/input/" in stream.namelist()
        assert "release-1.0.0/output/" in stream.namelist()
    assert archive.with_name(archive.name + ".sha256").read_text().split()[0] == package.digest(archive)


def test_launcher_uses_argument_array_and_no_global_environment_changes(tmp_path, monkeypatch):
    path = SCRIPTS.parent / "runtime/windows-distribution/avatar_runtime.py"
    spec = importlib.util.spec_from_file_location("avatar_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    audio = put(tmp_path, "space & % !/audio.wav")
    avatar = put(tmp_path, "space & % !/avatar.mp4")
    output = tmp_path / "result.mp4"
    calls = []
    monkeypatch.setattr(launcher.subprocess, "call", lambda *a, **kw: calls.append((a, kw)) or 0)
    monkeypatch.setattr(sys, "argv", ["launcher", "render", "--audio", str(audio),
                                    "--avatar", str(avatar), "--output", str(output)])
    assert launcher.main() == 0
    command = calls[0][0][0]
    assert command[command.index("--audio") + 1] == str(audio.resolve())
    assert command[command.index("--batch-size") + 1] == "1"
    assert calls[0][1].get("shell") is None
