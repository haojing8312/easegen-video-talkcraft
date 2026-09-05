from __future__ import annotations

from enum import Enum
import importlib.util
import multiprocessing
from pathlib import Path
import queue
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "win_onnx_native.py"
SPEC = importlib.util.spec_from_file_location("win_onnx_native_test", SCRIPT)
assert SPEC and SPEC.loader
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)


def test_queues_preserve_backpressure_and_cancellation():
    workers = native._ThreadWorkers()
    value = workers.Queue(1)
    value.put("first")
    with pytest.raises(queue.Full):
        value.put("second", timeout=0.01)
    assert value.get(timeout=0.1) == "first"
    assert value.ready.is_set()
    workers.close()
    with pytest.raises(native._Stopped):
        value.get()


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), -1])
def test_queue_operations_reject_unbounded_invalid_timeouts(timeout):
    workers = native._ThreadWorkers()
    incoming = workers.Queue(1)
    with pytest.raises(ValueError, match="finite and non-negative"):
        incoming.get(timeout=timeout)
    with pytest.raises(ValueError, match="finite and non-negative"):
        incoming.put("data", timeout=timeout)
    assert incoming.empty()
    workers.close()


@pytest.mark.parametrize("options, message", [
    ({"startup_timeout": float("nan")}, "finite and positive"),
    ({"startup_timeout": float("inf")}, "finite and positive"),
    ({"startup_timeout": float("-inf")}, "finite and positive"),
    ({"startup_timeout": 0}, "finite and positive"),
    ({"face_id": -1}, "non-negative integer"),
])
def test_render_rejects_invalid_parameters_before_loading_native_runtime(tmp_path, monkeypatch, options, message):
    def unexpected_import(name):
        pytest.fail("Invalid parameters must not load the native runtime")

    monkeypatch.setattr(native.importlib, "import_module", unexpected_import)
    parameters = dict(batch_size=1, face_enhancement=False, face_id=0, startup_timeout=1)
    parameters.update(options)
    with pytest.raises(ValueError, match=message):
        native.render_native(tmp_path, tmp_path / "voice.wav", tmp_path / "avatar.mp4", **parameters)


def test_startup_failure_is_reported_without_hanging():
    workers = native._ThreadWorkers()

    def audio_transfer():
        raise MemoryError("model allocation failed")

    worker = workers.Process(target=audio_transfer)
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="MemoryError.*model allocation failed"):
            workers.wait_ready([workers.Queue()], 0.5)
    finally:
        workers.close()


def test_startup_timeout_is_not_readiness():
    workers = native._ThreadWorkers()
    with pytest.raises(TimeoutError, match="not ready"):
        workers.wait_ready([workers.Queue()], 0.01)
    workers.close()


@pytest.mark.parametrize("mode", ["success", "render_failure", "escape", "batch_mismatch", "missing_session", "cpu_only"])
def test_render_contract_scopes_workers_and_config(tmp_path, monkeypatch, mode):
    workspace = tmp_path / "workspace with spaces & %name%!"
    workspace.mkdir()
    originals = tmp_path / "user source & %name%!"
    originals.mkdir()
    audio, avatar = originals / "voice & one.wav", originals / "avatar & two.mp4"
    audio.write_bytes(b"audio")
    avatar.write_bytes(b"video")
    monkeypatch.chdir(workspace)
    config = SimpleNamespace(batch_size="4", temp_dir="old-temp", result_dir="old-result", chaofen_before=1)

    class Status(Enum):
        run = 1
        success = 2
        error = 3

    providers = ["CPUExecutionProvider"] if mode == "cpu_only" else ["CUDAExecutionProvider", "CPUExecutionProvider"]
    session = SimpleNamespace(get_providers=lambda: providers,
                              get_inputs=lambda: [SimpleNamespace(name="source", type="tensor(float)")])
    model = lambda *a, **kw: SimpleNamespace(session=None if mode == "missing_session" else session)
    service = SimpleNamespace(Process=multiprocessing.Process, multiprocessing=multiprocessing,
                              DigitalHumanModel=model, Status=Status,
                              cv2=None, drivered_video=lambda: None,
                              GlobalConfig=SimpleNamespace(instance=lambda: config))

    def audio_transfer(incoming, outgoing, batch):
        service.DigitalHumanModel()
        while True:
            incoming.get()

    def init_wh_process(incoming, outgoing):
        while True:
            incoming.get()

    class Task:
        @classmethod
        def instance(cls):
            task = cls()
            cls._instance = task
            return task

        def __init__(self):
            self.batch_size = 4 if mode == "batch_mismatch" else int(config.batch_size)
            self.task_dic = {}
            self.drivered_queue = service.multiprocessing.Queue(10)
            self.output_imgs_queue = service.multiprocessing.Queue(10)
            self.init_wh_queue = service.multiprocessing.Queue(2)
            self.init_wh_queue_output = service.multiprocessing.Queue(2)
            service.Process(target=audio_transfer, args=(self.drivered_queue, self.output_imgs_queue, self.batch_size), daemon=True).start()
            service.Process(target=init_wh_process, args=(self.init_wh_queue, self.init_wh_queue_output), daemon=True).start()

        def work(self, audio_path, video_path, code, watermark, auth, chaofen, pn, target_face_id=0):
            assert mode not in ("missing_session", "cpu_only"), "Unverified CUDA must fail before work()"
            assert self.drivered_queue.ready.is_set() and self.init_wh_queue.ready.is_set()
            assert (audio_path, video_path) == ("input/audio.wav", "input/avatar.mp4")
            assert Path(audio_path).read_bytes() == b"audio"
            assert Path(video_path).read_bytes() == b"video"
            assert (config.temp_dir, config.result_dir) == ("./temp", "./result")
            assert (watermark, auth, chaofen, pn, target_face_id, self.face_id) == (0, 0, 0, 0, 2, 2)
            assert self.task_dic[code] == (Status.run, 0, "", "")
            assert config.chaofen_before == 0
            assert sys.argv == ["runner"]
            if mode == "render_failure":
                self.task_dic[code] = (Status.error, 0, "", "CUDA out of memory")
                return
            output = (tmp_path if mode == "escape" else workspace / config.result_dir) / "result.mp4"
            output.write_bytes(b"rendered-video")
            self.task_dic[code] = (Status.success, 100, str(output), "done")

    service.TransDhTask = Task
    monkeypatch.setitem(sys.modules, "service.trans_dh_service", service)
    monkeypatch.setattr(sys, "argv", ["runner", "--batch-size", "1"])
    original_process = multiprocessing.Process
    if mode == "success":
        result = native.render_native(workspace, audio, avatar, batch_size=1,
                                      face_enhancement=False, face_id=2, startup_timeout=1)
        assert result["batchSize"] == 1
        assert result["executionMode"] == "native-threads"
        assert result["workerCount"] == 2
        assert "CUDAExecutionProvider" in result["providers"]
        assert Path(result["output"]).read_bytes() == b"rendered-video"
    else:
        message = {"render_failure": "CUDA out of memory", "escape": "escaped", "batch_mismatch": "ignored batch_size",
                   "missing_session": "Could not observe an actual DINet", "cpu_only": "no CUDAExecutionProvider"}[mode]
        with pytest.raises(RuntimeError, match=message):
            native.render_native(workspace, audio, avatar, batch_size=1,
                                 face_enhancement=False, face_id=2, startup_timeout=1)
    assert service.Process is original_process
    assert multiprocessing.Process is original_process
    assert service.multiprocessing is multiprocessing
    assert service.DigitalHumanModel is model
    assert vars(config) == dict(batch_size="4", temp_dir="old-temp", result_dir="old-result", chaofen_before=1)
    assert sys.argv == ["runner", "--batch-size", "1"]
    assert audio.read_bytes() == b"audio"
    assert avatar.read_bytes() == b"video"
    assert (workspace / "input" / "audio.wav").read_bytes() == b"audio"
    assert (workspace / "input" / "avatar.mp4").read_bytes() == b"video"


def test_input_staging_keeps_already_staged_files(tmp_path, monkeypatch):
    incoming = tmp_path / "input"
    incoming.mkdir()
    audio, avatar = incoming / "audio.wav", incoming / "avatar.mp4"
    audio.write_bytes(b"audio-original")
    avatar.write_bytes(b"video-original")
    with monkeypatch.context() as patch:
        patch.setattr(native.shutil, "copyfileobj", lambda *args: pytest.fail("Same-path inputs must not be copied"))
        assert native._stage_inputs(tmp_path, audio, avatar) == ("input/audio.wav", "input/avatar.mp4")
    assert audio.read_bytes() == b"audio-original" and avatar.read_bytes() == b"video-original"


def test_input_staging_refuses_existing_unrelated_files(tmp_path):
    incoming = tmp_path / "input"
    incoming.mkdir()
    unrelated = incoming / "audio.wav"
    unrelated.write_bytes(b"keep-me")
    audio, avatar = tmp_path / "original.wav", tmp_path / "original.mp4"
    audio.write_bytes(b"audio")
    avatar.write_bytes(b"video")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        native._stage_inputs(tmp_path, audio, avatar)
    assert unrelated.read_bytes() == b"keep-me"
    assert not (incoming / "avatar.mp4").exists()


def test_input_staging_rejects_directory_reparse_point(tmp_path, monkeypatch):
    incoming = tmp_path / "input"
    incoming.mkdir()
    original = Path.lstat

    def linked_attributes(path):
        if path == incoming:
            return SimpleNamespace(st_file_attributes=0x400, st_mode=original(path).st_mode)
        return original(path)

    monkeypatch.setattr(Path, "lstat", linked_attributes)
    with pytest.raises(RuntimeError, match="not a link"):
        native._stage_inputs(tmp_path, tmp_path / "voice.wav", tmp_path / "avatar.mp4")


def test_streaming_reader_repeats_template_and_keeps_tail_frames():
    captures = []

    class Capture:
        def __init__(self, path):
            self.frames = iter(["frame-a", "frame-b"])
            self.closed = False
            captures.append(self)

        def read(self):
            frame = next(self.frames, None)
            return frame is not None, frame

        def release(self):
            self.closed = True

    incoming = queue.Queue()
    native._stream_video(SimpleNamespace(VideoCapture=Capture), "code", incoming,
                         "avatar.mp4", [1, 2, 3, 4, 5], 4, wh=0.8, target_face_id=2)
    assert incoming.get_nowait() == [["frame-a", "frame-b", "frame-a", "frame-b"],
                                    [1, 2, 3, 4], "code", 0.8, 4, 0, 2]
    assert incoming.get_nowait() == [["frame-a"], [5], "code", 0.8, 5, 0, 2]
    assert incoming.get_nowait() == [True, "success", "code"]
    assert len(captures) == 3 and all(cap.closed for cap in captures)


def test_streaming_reader_rejects_empty_template_without_endless_retries():
    cap = SimpleNamespace(read=lambda: (False, None), release=lambda: None)
    with pytest.raises(RuntimeError, match="no readable frames"):
        native._stream_video(SimpleNamespace(VideoCapture=lambda path: cap), "code",
                             queue.Queue(), "empty.mp4", [1], 1)
