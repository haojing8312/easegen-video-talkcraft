from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "win_onnx_media.py"
SPEC = importlib.util.spec_from_file_location("easegen_win_onnx_media", SCRIPT)
assert SPEC and SPEC.loader
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)


@pytest.fixture
def fake_media(tmp_path: Path, monkeypatch):
    output, audio, avatar = (tmp_path / name for name in ("output.mp4", "audio.wav", "avatar.mp4"))
    for path in (output, audio, avatar):
        path.write_bytes(path.name.encode())
    info = {"format": {"duration": "2.0"}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "duration": "2.0", "width": 160, "height": 96},
        {"codec_type": "audio", "codec_name": "aac", "duration": "2.0"},
    ]}
    narration = {"format": {"duration": "2.0"}, "streams": [{"codec_type": "audio"}]}
    monkeypatch.setattr(media, "probe", lambda path: info if path == output else narration)
    decode_calls = []

    def decode(command, **kwargs):
        decode_calls.append(command)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(media.subprocess, "run", decode)
    return SimpleNamespace(output=output, audio=audio, avatar=avatar, info=info,
                           narration=narration, decode_calls=decode_calls)


def validate(fixture):
    return media.validate_media(fixture.output, fixture.audio, fixture.avatar)


def test_valid_media_requires_full_audio_and_video_decode(fake_media):
    report = validate(fake_media)
    assert report["fullDecode"] is True
    assert report["durationSeconds"] == 2.0
    assert report["sha256"] == hashlib.sha256(fake_media.output.read_bytes()).hexdigest()
    command, = fake_media.decode_calls
    assert "-xerror" in command
    assert "0:v:0" in command and "0:a:0" in command


@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_empty_output_refused(fake_media, missing):
    if missing:
        fake_media.output.unlink()
    else:
        fake_media.output.write_bytes(b"")
    with pytest.raises(RuntimeError, match="missing or empty"):
        validate(fake_media)
    assert not fake_media.decode_calls


@pytest.mark.parametrize("missing_type", ["audio", "video"])
def test_output_requires_both_streams(fake_media, missing_type):
    fake_media.info["streams"] = [stream for stream in fake_media.info["streams"] if stream["codec_type"] != missing_type]
    with pytest.raises(RuntimeError, match="both video and narration audio"):
        validate(fake_media)


def test_narration_input_without_audio_is_rejected(fake_media):
    fake_media.narration["streams"] = [{"codec_type": "video"}]
    with pytest.raises(RuntimeError, match="narration input has no audio"):
        validate(fake_media)


@pytest.mark.parametrize("duration", ["0", "0.5", "3.0", "nan", "inf", "-inf"])
def test_invalid_or_mismatched_output_duration_rejected(fake_media, duration):
    fake_media.info["format"]["duration"] = duration
    with pytest.raises(RuntimeError):
        validate(fake_media)


@pytest.mark.parametrize("duration", ["nan", "inf", "-inf", "0"])
def test_invalid_narration_duration_rejected(fake_media, duration):
    fake_media.narration["format"]["duration"] = duration
    with pytest.raises(RuntimeError):
        validate(fake_media)


@pytest.mark.parametrize("stream_index", [0, 1])
@pytest.mark.parametrize("duration", ["0.4", "nan", "inf"])
def test_truncated_or_invalid_individual_stream_rejected(fake_media, stream_index, duration):
    fake_media.info["streams"][stream_index]["duration"] = duration
    with pytest.raises(RuntimeError):
        validate(fake_media)


def test_missing_container_duration_rejected(fake_media):
    fake_media.info["format"] = {}
    with pytest.raises(RuntimeError):
        validate(fake_media)


def test_unchanged_avatar_cannot_be_reported_as_generated_video(fake_media):
    fake_media.output.write_bytes(fake_media.avatar.read_bytes())
    with pytest.raises(RuntimeError, match="unchanged copy"):
        validate(fake_media)
    assert not fake_media.decode_calls


def test_decode_errors_reject_output(fake_media, monkeypatch):
    monkeypatch.setattr(media.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="corrupted frame"))
    with pytest.raises(RuntimeError, match="full decode.*corrupted frame"):
        validate(fake_media)


def test_probe_failure_is_not_converted_to_success(fake_media, monkeypatch):
    def fail_probe(path):
        raise subprocess.CalledProcessError(1, ["ffprobe", str(path)], stderr="invalid data")
    monkeypatch.setattr(media, "probe", fail_probe)
    with pytest.raises(subprocess.CalledProcessError):
        validate(fake_media)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg and ffprobe required")
def test_real_ffmpeg_fixture_decodes_and_rejects_silent_output(tmp_path: Path):
    audio = tmp_path / "narration.wav"
    avatar = tmp_path / "avatar.mp4"
    output = tmp_path / "generated.mp4"
    commands = [
        ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-t", "1", "-c:a", "pcm_s16le", str(audio)],
        ["-f", "lavfi", "-i", "color=c=blue:s=160x96:r=25:d=1", "-c:v", "mpeg4", str(avatar)],
        ["-f", "lavfi", "-i", "color=c=green:s=160x96:r=25:d=1", "-i", str(audio),
         "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(output)],
    ]
    for args in commands:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, check=True, timeout=30)
    report = media.validate_media(output, audio, avatar)
    assert report["fullDecode"] is True
    assert abs(report["durationSeconds"] - 1) < 0.25
    with pytest.raises(RuntimeError, match="both video and narration audio"):
        media.validate_media(avatar, audio, output)
