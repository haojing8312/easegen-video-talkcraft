#!/usr/bin/env python3
"""Build a separate, sanitized Windows avatar distribution; never edit the source.

The publisher must hold redistribution permission for all included components.
Build to a NEW directory outside both the source runtime and the Skill repository.
The archive contains no personal media; run acceptance tests outside the package.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import zipfile

from win_onnx_workspace import CODE_DIRECTORIES, CODE_SUFFIXES, MODEL_SUFFIXES, ROOT_MODULES

SKILL = Path(__file__).resolve().parents[1]
ADAPTERS = (
    "heygem_win_onnx_bridge.py", "heygem_win_onnx_runner.py", "win_onnx_native.py",
    "win_onnx_media.py", "win_onnx_workspace.py", "win_process_job.py",
)
MEDIA = frozenset({
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus",
    ".mp4", ".mov", ".avi", ".webm", ".mkv", ".wmv", ".m4v",
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff",
})
EXCLUDE_DIRS = frozenset({
    "__pycache__", ".git", ".cache", "cache", "caches", ".pytest_cache",
    "test", "tests", "log", "logs", "tmp", "temp", "change", "result",
    "output", "outputs", "face_cache", "pre_save", "save", "flagged",
    "conda-meta", "nsight-compute", "libnvvp", "compute-sanitizer",
})
EXCLUDE_NAMES = frozenset({"direct_url.json", ".netrc", "_netrc", ".npmrc", ".pypirc", "pip.ini", "pip.conf", "pyvenv.cfg"})
PYTHON_DIRS = frozenset({"DLLs", "Lib", "Library", "Scripts", "ffmpeg", "etc", "share", "libs", "include"})
CLEAN_INI = """[log]
log_dir = ./log
log_file = dh.log
[http_server]
server_ip = 127.0.0.1
server_port = 8383
[temp]
temp_dir = ./temp
clean_switch = 1
[result]
result_dir = ./result
clean_switch = 0
[digital]
batch_size = 1
[register]
url = http://127.0.0.1:12120
report_interval = 10
enable = 0
"""


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def excluded(path: Path, relative: Path) -> str | None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return "links"
    if any(part.lower() in EXCLUDE_DIRS for part in relative.parts):
        return "mutable-cache-test-or-developer-tools"
    if path.suffix.lower() in MEDIA:
        return "audio-video-images"
    if path.name.lower() in EXCLUDE_NAMES or path.name.lower().startswith(".env"):
        return "machine-configuration"
    if path.suffix.lower() in {".log", ".zip", ".7z", ".rar", ".pdb", ".key"}:
        return "logs-archives-debug-or-keys"
    return None


def copy_tree(source: Path, target: Path, counts: Counter, *, python: bool = False) -> None:
    copies = []
    for directory, folders, files in os.walk(source, followlinks=False):
        base = Path(directory)
        for name in folders[:]:
            child = base / name
            reason = excluded(child, child.relative_to(source))
            if reason:
                folders.remove(name)
                counts[reason] += 1
        for name in files:
            child = base / name
            relative = child.relative_to(source)
            reason = excluded(child, relative)
            notice = name.lower().startswith(("license", "licence", "notice", "copying", "copyright"))
            if reason or (not python and child.suffix.lower() not in CODE_SUFFIXES | MODEL_SUFFIXES and not notice):
                counts[reason or "outside-code-and-model-allowlist"] += 1
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copies.append((child, destination))
    # Small installed dependency files are slow with serial Windows file scanning.
    # Bounded parallel real copies retain isolation from source files.
    print(f"  {source.name}: {len(copies)} selected files", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda pair: shutil.copy2(*pair), copies))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def build(source: Path, destination: Path, version: str) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    for protected in (source, SKILL):
        if destination == protected or protected in destination.parents or destination in protected.parents:
            raise ValueError("output must be separate from the source runtime and Skill repository")
    if destination.exists():
        raise FileExistsError("output already exists; use a new release directory")
    required = ("py39/python.exe", "service/trans_dh_service.cp310-win_amd64.pyd", "config/config.ini")
    for name in required:
        if not (source / name).is_file():
            raise FileNotFoundError(name)
    destination.mkdir(parents=True)
    counts = Counter()
    print("Copying sanitized runtime (source is read-only)...", flush=True)
    for name in CODE_DIRECTORIES:
        if name != "config" and (source / name).is_dir():
            copy_tree(source / name, destination / "engine" / name, counts)
    for name in ROOT_MODULES:
        if (source / name).is_file():
            shutil.copy2(source / name, destination / "engine" / name)
    for name in PYTHON_DIRS:
        if (source / "py39" / name).is_dir():
            copy_tree(source / "py39" / name, destination / "engine" / "py39" / name, counts, python=True)
    for child in (source / "py39").iterdir():
        if child.is_file() and not excluded(child, Path(child.name)) and (child.suffix.lower() in {".exe", ".dll", ".txt"}):
            shutil.copy2(child, destination / "engine" / "py39" / child.name)
    write_text(destination / "engine/config/config.ini", CLEAN_INI)
    write_text(destination / "engine/config/config.json", '{"chaofen":"n"}\n')
    write_text(destination / "engine/face_lib/face.json", '{"face_id":0}\n')
    for name in ADAPTERS:
        write_text(destination / "adapter" / name, (SKILL / "scripts" / name).read_text(encoding="utf-8"))
    assets = SKILL / "runtime" / "windows-distribution"
    for name in ("avatar_runtime.py", "README.txt", "check.cmd", "render.cmd"):
        shutil.copy2(assets / name, destination / name)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        write_text(destination / "licenses" / name, (SKILL / name).read_text(encoding="utf-8"))
    for child in source.iterdir():
        if child.is_file() and child.name.lower().startswith(("license", "licence", "notice", "copying", "copyright")):
            shutil.copy2(child, destination / "licenses" / ("engine-" + child.name))
    for name in ("input", "output"):
        (destination / name).mkdir()
    manifest = {
        "name": "easegen-avatar-runtime-win-x64", "version": version,
        "backend": "heygem-win-onnx", "engineRelativePath": "engine",
        "python": "3.10.16 (directory name py39 retained)", "onnxruntime": "1.23.2",
        "redistribution": "Publisher confirmed permission; third-party terms remain applicable.",
        "scope": "Digital-human stage only; no IndexTTS2, alignment or Remotion environment.",
        "hardware": "NVIDIA CUDA required. RTX 2070 8GB short-clip tested; 4GB/6GB unverified.",
        "privacy": {"personalMediaIncluded": False, "excludedCounts": dict(counts),
                    "configuration": "Fresh loopback config, registration off, batch 1, enhancement off"},
        "files": [],
    }
    print("Hashing and checking final package inventory...", flush=True)
    files = sorted(path for path in destination.rglob("*") if path.is_file())
    def entry(path):
        if path.suffix.lower() in MEDIA:
            raise ValueError("Media unexpectedly entered package")
        return {"path": path.relative_to(destination).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        manifest["files"] = list(pool.map(entry, files))
    write_text(destination / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def archive(destination: Path) -> Path:
    target = destination.with_name(destination.name + ".zip")
    if target.exists():
        raise FileExistsError(target)
    print("Creating ZIP64 archive...", flush=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as output:
        for name in ("input", "output"):
            output.writestr(f"{destination.name}/{name}/", b"")
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                output.write(path, Path(destination.name) / path.relative_to(destination))
    print("Testing archive CRC...", flush=True)
    with zipfile.ZipFile(target) as output:
        bad = output.testzip()
        if bad:
            raise ValueError(f"archive CRC failure: {bad}")
    write_text(target.with_name(target.name + ".sha256"), f"{digest(target)}  {target.name}\n")
    return target


def refresh_adapters(destination: Path) -> None:
    """Refresh only Skill-owned adapters, without accepting extra runtime files."""
    path = destination / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {item["path"]: item for item in manifest["files"]}
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    if actual != set(expected) | {"manifest.json"}:
        raise ValueError("extra/missing files; clean or rebuild before refreshing adapters")
    for name in ADAPTERS:
        relative = "adapter/" + name
        item = expected[relative]
        target = destination / relative
        if digest(target) != item["sha256"]:
            raise ValueError(f"unexpected adapter modification: {relative}")
        write_text(target, (SKILL / "scripts" / name).read_text(encoding="utf-8"))
        item.update(bytes=target.stat().st_size, sha256=digest(target))
    write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--redistribution-confirmed", action="store_true", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--archive-only", action="store_true", help="Archive an already checked staging directory")
    modes.add_argument("--refresh-adapters", action="store_true", help="Refresh Skill adapters before re-testing a staging directory")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.version):
        parser.error("version must be a simple release identifier")
    destination = Path(args.output).resolve()
    if args.refresh_adapters:
        refresh_adapters(destination)
        print("Adapters refreshed; run acceptance again before archiving.")
        return
    if not args.archive_only:
        manifest = build(Path(args.source), destination, args.version)
        print(json.dumps({"staging": str(destination), "files": len(manifest["files"]),
                          "bytes": sum(item["bytes"] for item in manifest["files"])}), flush=True)
    else:
        # Refuse to package any post-build changes, including private test results.
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        expected = {item["path"]: item for item in manifest["files"]}
        actual = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        if actual != set(expected) | {"manifest.json"}:
            raise ValueError("staging file inventory changed; do not archive private test output")
        def verify(name):
            item = expected[name]
            if digest(destination / name) != item["sha256"]:
                raise ValueError(f"staging file changed: {name}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(verify, expected))
        print(json.dumps({"archive": str(archive(destination))}), flush=True)


if __name__ == "__main__":
    main()
