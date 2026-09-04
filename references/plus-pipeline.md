# Plus pipeline contract

Use this reference when the user wants the Skill to create narration and presenter footage instead of supplying finished media.

## Product boundary

All generation runs on the user's own computer. Do not add remote GPU rental, hosted inference, or an automatic cloud fallback. Model environments and weights stay outside the Skill directory so their Python, PyTorch, CUDA, and ONNX dependencies do not corrupt each other. The Skill stores no weights or secrets.

| Stage | Local execution | Current status |
| --- | --- | --- |
| IndexTTS2 | CPU, CUDA, MPS, or XPU when supported upstream | Integrated. CPU disables FP16, DeepSpeed, and CUDA kernels, but can be much slower than real time. |
| Easegen Digital Human v2 | NVIDIA CUDA through the Skill-owned standalone adapter (Windows + WSL or Linux) | Preferred Phase 1 backend. It leaves the production Redis/API/object-storage code unchanged. Verified on an RTX 2070 8 GB with a 3-second fixture. |
| HeyGem API | NVIDIA CUDA through a loopback/local-network API | Compatibility backend for an already running local HeyGem service. |
| DH_live_mini | Windows CPU through Easegen's audited adapter | Experimental CPU backend. Requires a preprocessed avatar package and a pinned upstream checkout. |
| Alignment | CPU | FireRedASR2-CTC int8 by default; faster-whisper is the lighter-install fallback. |
| Remotion | CPU or browser GPU acceleration | Final render uses concurrency 1. |

Phase 1 is accepted when IndexTTS2 plus `heygem-local` runs end to end on a documented NVIDIA configuration. Phase 2 is accepted only when a clean Windows CPU-only machine can install the selected TTS and avatar runtimes, render the reference fixture without CUDA, and pass the same duration, stream, face-zone, and TalkCraft handoff checks. A looping still/template video is not a CPU digital-human success.

## Inputs

- UTF-8 narration script; prefer one sentence per line.
- A clean 5–15 second voice reference WAV for IndexTTS2.
- A single-person avatar source MP4 with stable lighting, visible mouth, and no cuts.
- For `heygem-local`: an external `easegen-digitalhuman-v2` engine directory containing its native extensions and weights. The Skill supplies the standalone CLI code and does not modify the engine's production source or service behavior.
- For `heygem-api`: a HeyGem-compatible API running locally.
- For `dh-live`: a pinned DH_live checkout, its isolated Python, and `<avatars-root>/<avatar-code>/assets/{01.mp4,combined_data.json.gz}`.

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

## Phase 1: direct local runtime (recommended)

The direct backend keeps two responsibilities separate: the Skill owns the standalone CLI under `runtime/easegen-digitalhuman-v2-standalone/`, while an external engine directory supplies model weights, Linux native extensions, and the isolated Python 3.8 environment. It does not alter or import the production API, Redis scheduler, or object-storage result path. The native engine may still create its normal temporary media beside the engine during inference. On Windows it runs through WSL; on Linux it runs directly. The bridge consumes `EASEGEN_RESULT_JSON`, then the pipeline independently probes the generated MP4.

```powershell
python scripts/plus_pipeline.py init `
  --project-dir .local/my-talkcraft-plus `
  --script-file .local/input/script.txt `
  --voice-reference .local/input/voice.wav `
  --avatar-video .local/input/avatar.mp4 `
  --tts-backend indextts2-cli `
  --tts-device cuda:0 `
  --dh-backend heygem-local `
  --dh-engine-root F:\code\yzpd\easegen-digitalhuman-v2 `
  --dh-gpu 0
```

The engine path may instead be supplied to the standalone bridge with `EASEGEN_DIGITALHUMAN_ENGINE_ROOT`. Its default native warm-up is 30 seconds because the current compiled worker exposes no readiness signal. Override with `--dh-warmup-seconds` only after validating the target machine.

Before a full run, exercise the exact native environment:

```powershell
python scripts/heygem_local_bridge.py `
  --engine-root F:\code\yzpd\easegen-digitalhuman-v2 `
  --gpu 0 `
  --check
```

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

1. The selected backend reports success; `heygem-local` must return `EASEGEN_RESULT_JSON` with status `ok`, and HeyGem API must reach terminal status `3`.
2. The MP4 has a video stream and positive duration.
3. Presenter duration is within 0.25 seconds of narration.
4. Presenter content is not byte-identical to the avatar source.
5. `face_bbox.py` detects a face and writes a safe zone.
6. Alignment has no sentence marked `ok: false`.

`talkcraft-input.json` is only the handoff to SHOTBOOK and Remotion. It is not a finished-video claim.

## Runtime and release boundary

The Skill repository contains orchestration and standalone adapter code only. It must not redistribute model weights, private avatars, generated media, native binaries, or a third-party bundled environment. Before publishing an engine package, inventory every inherited model and binary, retain upstream notices, and confirm that redistribution and commercial use are allowed. A working local integration is not by itself a redistribution license.

## CPU roadmap

Use DH_live_mini as the first CPU fixture because it already offers no-training inference and a 39–52 MFLOPs/frame family. Prioritize a deterministic MP4 exporter around its Web/WASM path, which avoids the native mini 2.0 checkpoint availability problem, then benchmark visual quality and resource use on a clean CPU-only Windows machine. In parallel, evaluate FeatherTalk for a later portable engine: it offers ONNX/MNN CPU paths but requires per-avatar training. Do not use Wav2Lip as the default distributable backend because the official public weights are restricted to research, academic, and personal use.
