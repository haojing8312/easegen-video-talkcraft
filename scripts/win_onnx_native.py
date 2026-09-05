"""Adapt external HeyGem workers to threads in a disposable Windows subprocess.

The caller configures the external bundle's import paths and working directory.
This module never imports the bundle until render_native() is called. Each render
belongs in a fresh subprocess: native model state is released by process exit.
"""

from __future__ import annotations

import importlib
from functools import partial
import math
from pathlib import Path
import queue
import shutil
import stat
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any
import uuid


class _Stopped(BaseException):
    """Escape native workers that otherwise catch Exception and keep looping."""


class _ThreadWorkers:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.threads: list[threading.Thread] = []
        self.failures: queue.Queue = queue.Queue()
        owner = self

        class ReadyQueue(queue.Queue):
            def __init__(self, maxsize: int = 0):
                super().__init__(maxsize)
                self.ready = threading.Event()

            def get(self, block: bool = True, timeout: float | None = None):
                self.ready.set()
                return self._poll(super().get, queue.Empty, block, timeout)

            def put(self, item, block: bool = True, timeout: float | None = None):
                return self._poll(lambda **kw: super(ReadyQueue, self).put(item, **kw),
                                  queue.Full, block, timeout)

            @staticmethod
            def _poll(operation, retry, block, timeout):
                if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
                    raise ValueError("timeout must be finite and non-negative")
                deadline = None if timeout is None else time.monotonic() + timeout
                while True:
                    if owner.stop.is_set():
                        raise _Stopped()
                    if not block:
                        return operation(block=False)
                    remaining = None if deadline is None else deadline - time.monotonic()
                    try:
                        return operation(timeout=0.1 if remaining is None else max(0, min(0.1, remaining)))
                    except retry:
                        if deadline is not None and time.monotonic() >= deadline:
                            raise

        class ManagedThread(threading.Thread):
            def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
                super().__init__(group=group, target=target, name=name or getattr(target, "__name__", None),
                                 args=args, kwargs=kwargs or {}, daemon=True)
                self.persistent = getattr(target, "__name__", "") in {"audio_transfer", "init_wh_process"}
                owner.threads.append(self)

            def run(self):
                try:
                    super().run()
                    if self.persistent and not owner.stop.is_set():
                        raise RuntimeError("persistent worker exited unexpectedly")
                except _Stopped:
                    pass
                except BaseException as exc:
                    owner.failures.put((self.name, exc))

            def join(self, timeout=None):
                if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
                    raise ValueError("timeout must be finite and non-negative")
                deadline = None if timeout is None else time.monotonic() + timeout
                while self.is_alive():
                    owner.check()
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        return
                    super().join(0.1 if remaining is None else min(0.1, remaining))
                owner.check()

        self.Queue = ReadyQueue
        self.Process = ManagedThread

    def check(self) -> None:
        if not self.failures.empty():
            name, exc = self.failures.queue[0]
            raise RuntimeError(f"HeyGem worker {name} failed: {type(exc).__name__}: {exc}") from exc

    def wait_ready(self, inputs: list, timeout: float) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("startup_timeout must be finite and positive")
        deadline = time.monotonic() + timeout
        while not all(item.ready.is_set() for item in inputs):
            self.check()
            if time.monotonic() >= deadline:
                raise TimeoutError(f"HeyGem model workers were not ready within {timeout:g}s")
            self.stop.wait(0.05)
        self.check()

    def close(self) -> None:
        self.stop.set()
        # Bypass ManagedThread.join: cleanup must not replace the original error.
        deadline = time.monotonic() + 2
        for worker in self.threads:
            if worker.ident is not None:
                threading.Thread.join(worker, max(0, deadline - time.monotonic()))


def _validated_output(state: Any, workspace: Path) -> Path:
    if not isinstance(state, tuple) or len(state) != 4:
        raise RuntimeError(f"HeyGem returned an invalid task state: {state!r}")
    status, progress, value, message = state
    if getattr(status, "value", status) != 2:
        raise RuntimeError(f"HeyGem render failed at {progress}%: {message}; state={status!r}")
    if not isinstance(value, (str, Path)) or not str(value):
        raise RuntimeError("HeyGem success state contains no output path")
    output = Path(value)
    if not output.is_absolute():
        output = workspace / output
    output = output.resolve()
    if not output.is_relative_to(workspace):
        raise RuntimeError(f"HeyGem output escaped the isolated workspace: {output}")
    if output.suffix.lower() != ".mp4" or not output.is_file() or not output.stat().st_size:
        raise RuntimeError(f"HeyGem output is missing, empty, or not MP4: {output}")
    return output


def _stream_video(cv2, code, incoming, video_path, features, batch_size,
                  wh=0, chaofen_ctrl=0, target_face_id=0):
    """Repeat a short template without caching it; flush the final partial batch."""
    cap = cv2.VideoCapture(video_path)
    frames, audio_batch, read_in_pass = [], [], 0
    try:
        if len(features) == 0:
            raise ValueError("HeyGem returned no audio features")
        for index in range(len(features)):
            ok, frame = cap.read()
            if not ok:
                cap.release()
                if not read_in_pass:
                    raise RuntimeError("Avatar video has no readable frames")
                cap = cv2.VideoCapture(video_path)
                read_in_pass = 0
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Could not restart avatar video for narration")
            read_in_pass += 1
            frames.append(frame)
            audio_batch.append(features[index])
            if len(frames) == batch_size or index + 1 == len(features):
                incoming.put([frames, audio_batch, code, wh, index + 1, chaofen_ctrl, target_face_id],
                             block=True, timeout=60)
                frames, audio_batch = [], []
        incoming.put([True, "success", code], timeout=60)
    finally:
        cap.release()


def _local_directory(workspace: Path, name: str) -> Path:
    directory = workspace / name
    directory.mkdir(exist_ok=True)
    attributes = getattr(directory.lstat(), "st_file_attributes", 0)
    if (directory.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            or not directory.is_dir() or directory.resolve() != directory):
        raise RuntimeError(f"Native job directory must be a local directory, not a link: {directory}")
    return directory


def _stage_inputs(workspace: Path, audio: Path, avatar: Path) -> tuple[str, str]:
    """Keep caller paths out of the bundle's unquoted shell command strings."""
    directory = _local_directory(workspace, "input")
    copies = [(audio, directory / "audio.wav"), (avatar, directory / "avatar.mp4")]
    for source, destination in copies:
        if destination.exists() or destination.is_symlink():
            attributes = getattr(destination.lstat(), "st_file_attributes", 0)
            if (destination.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                    or source != destination or not destination.is_file()):
                raise FileExistsError(f"Refusing to overwrite or follow an existing staged input: {destination}")
    for source, destination in copies:
        if source != destination:
            # Exclusive creation also prevents an intervening link/file overwrite.
            with source.open("rb") as incoming, destination.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
    return "input/audio.wav", "input/avatar.mp4"


def render_native(workspace: Path, audio: Path, avatar: Path, *, batch_size: int,
                  face_enhancement: bool, face_id: int, startup_timeout: float = 120) -> dict:
    """Run one job using the bundle's service API, with bounded in-process queues."""
    workspace, audio, avatar = workspace.resolve(), audio.resolve(), avatar.resolve()
    if batch_size not in (1, 2, 4) or not math.isfinite(startup_timeout) or startup_timeout <= 0:
        raise ValueError("batch_size must be 1, 2, or 4; startup_timeout must be finite and positive")
    if not isinstance(face_id, int) or face_id < 0:
        raise ValueError("face_id must be a non-negative integer")
    if not workspace.is_dir() or not audio.is_file() or not avatar.is_file():
        raise FileNotFoundError("workspace, narration audio, and avatar video must exist")
    if Path.cwd().resolve() != workspace:
        raise RuntimeError("The native runner must set its working directory to the isolated workspace")
    staged_audio, staged_avatar = _stage_inputs(workspace, audio, avatar)

    service = importlib.import_module("service.trans_dh_service")
    config = service.GlobalConfig.instance()
    if hasattr(service.TransDhTask, "_instance"):
        raise RuntimeError("HeyGem was already initialized; render in a fresh subprocess")
    original = {name: getattr(service, name) for name in ("Process", "multiprocessing", "DigitalHumanModel", "drivered_video")}
    settings = {"batch_size": str(batch_size), "temp_dir": "./temp", "result_dir": "./result"}
    if not face_enhancement:
        # The native constructor only creates its pre-enhancement GFPGAN at == 1.
        settings["chaofen_before"] = 0
    previous = {name: getattr(config, name) for name in settings}
    workers, sessions = _ThreadWorkers(), []
    previous_argv = sys.argv

    def observed_model(*args, **kwargs):
        model = original["DigitalHumanModel"](*args, **kwargs)
        session = getattr(model, "session", None)
        if session is not None:
            sessions.append({"model": "DINet", "providers": session.get_providers(),
                             "inputs": [{"name": item.name, "type": item.type}
                                        for item in session.get_inputs()]})
        return model

    try:
        for name, value in settings.items():
            setattr(config, name, value)
        _local_directory(workspace, "temp")
        _local_directory(workspace, "result")
        service.Process = workers.Process
        # Replace this module's reference, never mutate multiprocessing itself.
        service.multiprocessing = SimpleNamespace(Queue=workers.Queue)
        service.DigitalHumanModel = observed_model
        service.drivered_video = partial(_stream_video, service.cv2)
        sys.argv = [previous_argv[0]]
        task = service.TransDhTask.instance()
        if int(task.batch_size) != batch_size:
            raise RuntimeError(f"HeyGem ignored batch_size: requested {batch_size}, actual {task.batch_size}")
        workers.wait_ready([task.drivered_queue, task.init_wh_queue], startup_timeout)
        if not sessions:
            raise RuntimeError("Could not observe an actual DINet ONNX session; cannot verify CUDA execution")
        if any("CUDAExecutionProvider" not in session["providers"] for session in sessions):
            raise RuntimeError(f"Actual DINet ONNX session has no CUDAExecutionProvider: {sessions!r}")
        task.face_id = face_id  # The native work() body reads this attribute.
        code = "easegen_" + uuid.uuid4().hex
        task.task_dic[code] = (service.Status.run, 0, "", "")
        task.work(staged_audio, staged_avatar, code, 0, 0, int(face_enhancement), 0, target_face_id=face_id)
        workers.check()
        output = _validated_output(task.task_dic.get(code), workspace)
        return {"output": str(output), "batchSize": int(task.batch_size),
                "faceEnhancement": face_enhancement, "faceId": face_id,
                "executionMode": "native-threads", "workerCount": len(workers.threads),
                "queueCapacity": {"input": task.drivered_queue.maxsize,
                                  "output": task.output_imgs_queue.maxsize},
                "providers": sorted({p for session in sessions for p in session["providers"]}),
                "sessions": sessions, "reader": "streaming-loop", "taskCode": code}
    finally:
        workers.close()
        for name, value in original.items():
            setattr(service, name, value)
        for name, value in previous.items():
            setattr(config, name, value)
        sys.argv = previous_argv
