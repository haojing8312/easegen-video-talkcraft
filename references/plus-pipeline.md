# Plus pipeline contract

Use this reference when the user wants the Skill to create narration and presenter footage instead of supplying finished media.

## Product boundary

All generation runs on the user's own computer. Do not add remote GPU rental, hosted inference, or an automatic cloud fallback. Model environments and weights stay outside the Skill directory so their Python, PyTorch, CUDA, and ONNX dependencies do not corrupt each other. The Skill stores no weights or secrets.

| Stage | Local execution | Current status |
| --- | --- | --- |
| IndexTTS2 | CPU, CUDA, MPS, or XPU when supported upstream | Integrated. CPU disables FP16, DeepSpeed, and CUDA kernels, but can be much slower than real time. |
| HeyGem Windows ONNX | Native Windows + external Python 3.10/CUDA bundle | Windows default, no WSL. Batch 1, optional enhancement, threaded workers and isolated job directories. See [Windows guide](windows-onnx.md) for measured scope. |
| Easegen Digital Human v2 | NVIDIA CUDA through the Skill-owned Linux standalone adapter | Linux compatibility backend. It leaves production Redis/API/object-storage code unchanged. |
| HeyGem API | NVIDIA CUDA through a loopback/local-network API | Compatibility backend for an already running local HeyGem service. |
| DH_live_mini | Windows CPU through Easegen's audited adapter | Experimental CPU backend. Requires a preprocessed avatar package and a pinned upstream checkout. |
| Alignment | CPU | FireRedASR2-CTC int8 by default; faster-whisper is the lighter-install fallback. |
| Remotion | CPU or browser GPU acceleration | Final render uses concurrency 1. |

Phase 1 requires IndexTTS2 plus the selected GPU backend to run end to end on a documented NVIDIA configuration. An individual native digital-human smoke test is not proof of the full TTS/alignment/Remotion pipeline. Phase 2 is accepted only when a clean Windows CPU-only machine can install the selected TTS and avatar runtimes, render the reference fixture without CUDA, and pass the same duration, stream, face-zone, and TalkCraft handoff checks. Replaying an unchanged template is not a CPU digital-human success.

## Inputs

- UTF-8 narration script; prefer one sentence per line.
- A clean 5–15 second voice reference WAV for IndexTTS2.
- A single-person avatar source MP4 with stable lighting, visible mouth, and no cuts.
- For `heygem-win-onnx`: a compatible external Windows ONNX bundle with Python 3.10, CUDA dependencies and weights; see [exact prerequisites and CLI](windows-onnx.md). The bundle is not included or automatically downloaded.
- For `heygem-local`: an external `easegen-digitalhuman-v2` engine directory containing its native extensions and weights. The Skill supplies the standalone CLI code and does not modify the engine's production source or service behavior.
- For `heygem-api`: a HeyGem-compatible API running locally.
- For `dh-live`: a pinned DH_live checkout, its isolated Python, and `<avatars-root>/<avatar-code>/assets/{01.mp4,combined_data.json.gz}`.

## Obtaining the digital-human runtime

The repository intentionally excludes HeyGem/Duix model weights, Docker images, native extensions, and bundled environments because they are large and independently licensed.

- **Maintainer-assisted path:** contact the Easegen maintainers through this repository's Issues for paid deployment, environment setup, low-VRAM adaptation, or an independently delivered runtime package where redistribution is authorized. Payment covers the stated integration/support service; it does not by itself grant rights to third-party code, models, images, voices, or commercial use.
- **Self-managed path:** clone the current official project at [duixcom/Duix-Avatar](https://github.com/duixcom/Duix-Avatar), follow its deployment and license documentation, and adapt it locally. For API integration, add a loopback-only compatibility layer that maps the official `/easy/submit` and `/easy/query` endpoints to the `/api/v1/easedh/task/create` and `/api/v1/easedh/task/result` contract expected by `heygem-api`. For direct integration, adapt the inference entrypoint to emit the `EASEGEN_RESULT_JSON` contract required by `heygem-local`. The official checkout does not directly match either Easegen contract or the standalone engine directory layout.

Never download or redistribute a community bundle solely because a public link exists. Preserve upstream notices and verify the current license for every code, model, image, and native-binary component.

## Project layout

`init` writes the manifest. `run` preserves diagnostics and writes deterministic artifacts:

```text
project/
├── plus-manifest.json
├── run-state.json
├── input/{script.txt,script.json,voice-reference.wav,avatar.mp4}
├── audio/{full.wav,timestamps.json}
├── presenter/{host.mp4,face-zone.json}
├── remotion-input/timing.json
└── talkcraft-input.json
```

Machine-specific manifests belong under the repository's ignored `.local/` directory.

## Phase 1: native Windows (default on Windows)

The Skill owns the Windows bridge and thread/streaming adapters. The external bundle supplies its existing interpreter, native extensions and models. Each render uses a fresh workspace beneath `presenter/.heygem-jobs/`; generated state and configuration edits stay there. No WSL, production API, Redis scheduler or object-storage service is loaded. Windows Job Objects reclaim subprocesses on timeout or termination. See [Windows implementation and limitations](windows-onnx.md).

```powershell
python scripts/plus_pipeline.py init `
  --project-dir .local/my-talkcraft-plus `
  --script-file .local/input/script.txt `
  --voice-reference .local/input/voice.wav `
  --avatar-video .local/input/avatar.mp4 `
  --tts-backend indextts2-cli `
  --tts-device cuda:0 `
  --dh-backend heygem-win-onnx `
  --dh-engine-root F:\worksoft\heygem-win-50-onnx `
  --dh-batch-size 1 `
  --dh-gpu 0
```

The standalone Windows bridge also accepts `EASEGEN_HEYGEM_WIN_ONNX_ROOT`. `--dh-startup-timeout` bounds model-worker readiness waiting (default 120 seconds), not a fixed sleep. `--dh-timeout` bounds the runner process including initialization. `--dh-face-enhancement` is opt-in; `--dh-face-id` selects the native face index. UI-specific `steps`, `low` and `multiFace` are not part of this direct-service contract.

Before a full run, exercise the exact native environment:

```powershell
python scripts/heygem_win_onnx_bridge.py `
  --runtime-root F:\worksoft\heygem-win-50-onnx `
  --gpu 0 `
  --check
```

This check lists available providers and required files only: CUDA DLL loading and actual inference are verified by a real render, not by `--check`.

## Compatibility: direct Linux runtime

On Linux, select `--dh-backend heygem-local --dh-engine-root /path/to/external-engine`.
The Skill owns `runtime/easegen-digitalhuman-v2-standalone/`, while the external engine provides its Linux native extensions, Python 3.8 environment and weights. This older adapter can still create native temporary media beside the engine. Its default fixed warm-up remains 30 seconds (`--dh-warmup-seconds`); it consumes `EASEGEN_RESULT_JSON`. Windows invocation now fails with guidance to use `heygem-win-onnx` rather than launching WSL.

## Compatibility: local HeyGem API

```powershell
python scripts/plus_pipeline.py init `
  --project-dir .local/my-talkcraft-plus `
  --script-file .local/input/script.txt `
  --voice-reference .local/input/voice.wav `
  --avatar-video .local/input/avatar.mp4 `
  --tts-backend indextts2-cli `
  --tts-device cuda:0 `
  --dh-backend heygem-api `
  --dh-api-base http://127.0.0.1:17863
```

HeyGem accepts URLs, so the runner starts a temporary local HTTP server for the audio and avatar and always stops it in `finally`. For Docker on the same computer, set `media.publicBaseUrl` in the manifest to `http://host.docker.internal:{port}`. Do not expose the port beyond the local machine.

## CPU experiment: DH_live_mini

```powershell
python scripts/plus_pipeline.py init `
  --project-dir .local/my-talkcraft-cpu `
  --script-file .local/input/script.txt `
  --voice-reference .local/input/voice.wav `
  --avatar-video .local/input/avatar.mp4 `
  --tts-device cpu `
  --dh-backend dh-live `
  --dh-live-root F:\models\DH_live `
  --dh-live-python F:\models\DH_live\.venv\Scripts\python.exe `
  --dh-live-avatars-root F:\models\DH_live\avatars `
  --dh-live-output-root F:\models\DH_live\outputs `
  --dh-avatar-code demo
```

Before running either profile:

```powershell
python scripts/plus_pipeline.py plan --project-dir .local/my-talkcraft-plus
python scripts/plus_pipeline.py preflight --project-dir .local/my-talkcraft-plus --offline
python scripts/plus_pipeline.py preflight --project-dir .local/my-talkcraft-plus
python scripts/plus_pipeline.py run --project-dir .local/my-talkcraft-plus
```

The direct TTS backend invokes the official `indextts2` CLI. The `easegen-cli` TTS backend is also supported for an already configured local Easegen service; it must not point to hosted inference.
If an isolated `uv` environment's generated `indextts2.exe` trampoline cannot resolve its original path, pass `--indextts-python <venv>\Scripts\python.exe`; the runner will use `python -m indextts.cli_v2` instead.

## Acceptance gates

The runner accepts presenter output only when all are true:

1. The selected backend reports success. Windows verifies native service status `2`, validates media, then emits `EASEGEN_WIN_ONNX_JSON` with status `ok`; `heygem-local` returns `EASEGEN_RESULT_JSON` with status `ok`. HeyGem API's terminal success value is `3` (different from the native enum).
2. The MP4 has both video and audio streams and positive duration. Windows additionally fully decodes both streams before atomic publication; a failed run cannot relabel an old output as a new success.
3. Presenter duration is within 0.25 seconds of narration.
4. Presenter content is not byte-identical to the avatar source.
5. `face_bbox.py` detects a face and writes a safe zone.
6. Alignment has no sentence marked `ok: false`.

`talkcraft-input.json` is only the handoff to SHOTBOOK and Remotion. It is not a finished-video claim.

## Runtime and release boundary

The Skill repository contains orchestration and standalone adapter code only. It must not redistribute model weights, private avatars, generated media, native binaries, or a third-party bundled environment. Before publishing an engine package, inventory every inherited model and binary, retain upstream notices, and confirm that redistribution and commercial use are allowed. A working local integration is not by itself a redistribution license.

## CPU roadmap

Use DH_live_mini as the first CPU fixture because it already offers no-training inference and a 39–52 MFLOPs/frame family. Prioritize a deterministic MP4 exporter around its Web/WASM path, which avoids the native mini 2.0 checkpoint availability problem, then benchmark visual quality and resource use on a clean CPU-only Windows machine. In parallel, evaluate FeatherTalk for a later portable engine: it offers ONNX/MNN CPU paths but requires per-avatar training. Do not use Wav2Lip as the default distributable backend because the official public weights are restricted to research, academic, and personal use.
