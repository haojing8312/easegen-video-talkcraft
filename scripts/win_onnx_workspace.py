"""Isolate the external HeyGem bundle's writable runtime state for one render.

Only known code/configuration roots enter the workspace. Model files may share
read-only usage through hard links; all code/configuration files are real copies.
Callers must treat weights as immutable, including files reached by a hard link.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
import shutil
import stat
import tempfile


CODE_DIRECTORIES = (
    "config", "face_attr_detect", "face_detect_utils", "face_lib", "h_utils",
    "landmark2face_wy", "model_lib", "pretrain_models", "service", "wenet",
    "y_utils", "mel",
)
ROOT_MODULES = ("digitalhuman_interface_onnx.pyc", "preprocess_audio_and_3dmm.pyc", "port.py")
MODEL_SUFFIXES = frozenset({".onnx", ".pth", ".pt", ".ckpt", ".safetensors"})
CODE_SUFFIXES = frozenset({
    ".py", ".pyc", ".pyd", ".dll", ".ini", ".json", ".yaml", ".yml",
    ".txt", ".npy", ".npz", ".dat",
})
MUTABLE_DIRECTORIES = (
    "log", "tmp", "temp", "change", "result", "output", "face_cache",
    "pre_save", "save",
)
EXCLUDED_DIRECTORIES = frozenset({
    "__pycache__", ".git", ".pytest_cache", "cache", "caches", "logs",
    "test", "tests", "flagged", *MUTABLE_DIRECTORIES,
})


def _is_reparse_point(path: Path) -> bool:
    """Do not follow symlinks or Windows junctions into mutable external trees."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _copy_file(source: Path, destination: Path) -> None:
    if _is_reparse_point(source):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in MODEL_SUFFIXES:
        try:
            os.link(source, destination)
            return
        except OSError:
            # Cross-volume destinations and filesystems without hard links work too.
            pass
    shutil.copy2(source, destination)


def _copy_code_tree(source: Path, destination: Path) -> None:
    if _is_reparse_point(source):
        return
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if _is_reparse_point(entry):
            continue
        target = destination / entry.name
        if entry.is_dir():
            if entry.name.lower() not in EXCLUDED_DIRECTORIES:
                _copy_code_tree(entry, target)
        elif entry.is_file() and entry.suffix.lower() in CODE_SUFFIXES | MODEL_SUFFIXES:
            _copy_file(entry, target)


def _configure_workspace(workspace: Path, batch_size: int) -> None:
    config_path = workspace / "config" / "config.ini"
    config = configparser.ConfigParser(interpolation=None)
    with config_path.open(encoding="utf-8-sig") as stream:
        config.read_file(stream)
    updates = {
        "digital": {"batch_size": str(batch_size)},
        "log": {"log_dir": "./log", "log_file": "dh.log"},
        "temp": {"temp_dir": "./temp"},
        "result": {"result_dir": "./result"},
        "register": {"enable": "0"},
    }
    for section, values in updates.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in values.items():
            config.set(section, key, value)
    with config_path.open("w", encoding="utf-8", newline="\n") as stream:
        config.write(stream)


def prepare_workspace(runtime: Path, output_parent: Path, batch_size: int) -> Path:
    """Create a fresh ``output_parent/.heygem-jobs/render-*`` directory.

    Set this directory as the native runner's working directory AND import root.
    Never run model conversion or mutate model files in it: models can be hard
    links to the supplied runtime. Generated caches, media, logs, and the modified
    batch-size configuration belong exclusively to this render. Workspaces are
    retained for diagnostics; the caller may remove them after the process exits.
    """
    runtime = Path(runtime).expanduser().resolve(strict=True)
    output_parent = Path(output_parent).expanduser().resolve()
    if not runtime.is_dir():
        raise NotADirectoryError(runtime)
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size not in (1, 2, 4):
        raise ValueError("batch_size must be 1, 2, or 4")
    if output_parent == runtime or runtime in output_parent.parents:
        raise ValueError("output_parent must be outside the original runtime")
    config_path = runtime / "config" / "config.ini"
    if not config_path.is_file() or _is_reparse_point(runtime / "config") or _is_reparse_point(config_path):
        raise FileNotFoundError(f"regular runtime configuration required: {config_path}")
    jobs_parent = output_parent / ".heygem-jobs"
    if jobs_parent.exists() and _is_reparse_point(jobs_parent):
        raise ValueError(".heygem-jobs must not be a symlink or junction")
    jobs_parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="render-", dir=jobs_parent))
    try:
        for source in runtime.glob("cy_app*.pyd"):
            if source.is_file():
                _copy_file(source, workspace / source.name)
        for name in ROOT_MODULES:
            source = runtime / name
            if source.is_file():
                _copy_file(source, workspace / name)
        for name in CODE_DIRECTORIES:
            source = runtime / name
            if source.is_dir():
                _copy_code_tree(source, workspace / name)
        for name in MUTABLE_DIRECTORIES:
            (workspace / name).mkdir(parents=True, exist_ok=True)
        _configure_workspace(workspace, batch_size)
    except Exception:
        # This is only the fresh directory created above, never the runtime tree.
        shutil.rmtree(workspace)
        raise
    return workspace
