# Native Windows HeyGem ONNX

Use `heygem-win-onnx` for a compatible, separately obtained Windows bundle.
This backend does not use WSL, Docker, Redis, object storage, remote GPU rental,
or the production `easegen-digitalhuman-v2` service. It still requires NVIDIA CUDA.
The bridge is not a universal adapter for every HeyGem/Duix distribution.

## Prerequisites

- Windows x64, NVIDIA driver and the bundle's compatible CUDA dependencies.
- A compatible bundle with `py39/python.exe` (the tested interpreter is actually
  Python **3.10.16**), `service/trans_dh_service.cp310-win_amd64.pyd`,
  `config/config.ini`, WeNet, face detection and DINet model assets.
- Tested ONNX Runtime: **1.23.2**. Do not upgrade the bundle's Python or native
  dependencies blindly: the compiled extensions have a CPython 3.10 ABI.
- `ffmpeg` and `ffprobe`, on PATH or in the bundle's `py39/ffmpeg/bin`.
- Authorized narration WAV and a single-person MP4 with a visible mouth.

The Skill repository contains only adapters, tests and instructions. It does not
redistribute the community bundle, native binaries, model weights or test media.
Obtain those separately with permission and review their licenses. An official
Duix checkout does not have this bundle's Python module/API layout automatically.

## Run one real test

From the Skill repository in PowerShell:

```powershell
python scripts/heygem_win_onnx_bridge.py `
  --runtime-root F:\worksoft\heygem-win-50-onnx --check

python scripts/heygem_win_onnx_bridge.py `
  --runtime-root F:\worksoft\heygem-win-50-onnx `
  --audio .local/input/voice.wav `
  --avatar .local/input/avatar.mp4 `
  --output .local/test/host.mp4 `
  --batch-size 1 --timeout 1800
```

`--check` is a lightweight **file and provider-availability** check. It deliberately
reports `cudaInferenceValidated: false`: an installed CUDA provider does not prove
the CUDA libraries load or inference works. Real rendering observes the DINet
session providers and rejects silent CPU-only fallback.

`--runtime-python` overrides the interpreter. `--startup-timeout` defaults to 120
seconds for worker readiness after service construction; the outer `--timeout`
bounds the whole runner, including imports and construction. Neither is a fixed
warm-up sleep. `--face-id` defaults to 0. `--face-enhancement` is opt-in and consumes
additional resources. Batch choices are 1, 2 and 4. UI-only `steps`, `low` and
`multiFace` are not exposed because this route calls the native service directly.

An existing output is refused unless `--overwrite` is supplied. Inputs and files
inside the original bundle cannot be output targets. A replacement is published
atomically only after the new result passes validation; failure preserves an old
output but reports failure. The Plus pipeline opts into this safe replacement for
reruns. Never treat a leftover `host.mp4` as proof the latest task succeeded.

For script → IndexTTS2 → presenter → TalkCraft handoff, see
[Plus pipeline](plus-pipeline.md), select `--dh-backend heygem-win-onnx`, and pass
the same external bundle with `--dh-engine-root`.

## What reduces resource use

| Change | Mechanism and trade-off |
| --- | --- |
| Batch 1 by default | Fewer simultaneous DINet inputs/activations. Less peak VRAM; throughput can be lower. Actual native batch is asserted, not merely written in a manifest. |
| Enhancement off | Sets native pre-enhancement off before model construction, avoiding that optional GFPGAN model. Enable only after measuring the quality/resource trade-off. |
| One disposable inference process | Model, analysis, reader and writer workers run as threads with bounded queues. Avoids repeatedly importing PyTorch/CUDA DLLs in Windows spawn workers and duplicate process contexts. Models still need their own memory. |
| Streaming template replay | Reads at most a batch at a time, with bounded queued batches. Does not retain every decoded template frame. Reopens at EOF and flushes partial tail batches. Memory is bounded by batch/queues and frame resolution, not total template duration. |
| One process lifetime per task | Exit releases model allocations; no concurrent TTS/GPU avatar models are intentionally retained by this pipeline. Startup repeats for each job. |

The stock sequential reader does not correctly handle a longer narration and its
partial final batch; the Skill replaces only that service entrypoint in memory.
Streaming replay loops forward rather than ping-ponging: a gesture discontinuity
at the template boundary remains possible. Choose a suitable template or cover
the boundary during final composition. This is resource management, not a new
lip-sync model or a guarantee of equal quality on every face.

FP16 conversion, INT8 quantization, TensorRT, CUDA I/O binding, shared model-session
caching and a fully CPU-only HeyGem stack are **not implemented or claimed** by
this change. The tested DINet model is FP32. We do not change system pagefile
settings, driver installations or the user's other GPU applications.

## Isolation and diagnostics

Each render creates `<output-parent>/.heygem-jobs/render-*/`:

- Explicitly selected code/configuration are copied; mutable output/cache
  directories are newly created. Source Python/config files are never rewritten.
- Weights are hardlinked on compatible same-volume filesystems, with copy fallback
  across volumes. **Weights must remain immutable**; hardlinks are not a security
  sandbox or write-protected copies. Never convert or edit them inside a job.
- All native working paths, TEMP/TMP, logs and generated media point at that job.
  The external Python installation is reused with bytecode writes disabled.
- User inputs are copied to fixed ASCII relative paths before entering the
  external engine's legacy shell-based FFmpeg calls. Space/special-character
  paths stay outside that shell boundary; native temp/result paths are relative.
- Bridge and runner own nested Windows Job Objects. Timeout or termination
  reclaims their descendants, including FFmpeg. Unrelated programs are not killed.
- `runner.log` and `report.json` are retained on both success and failure.
  Workspaces may contain private media and large copied weights. Keep them out of
  version control; delete only the specific finished job directory when no process
  uses it. The repository ignores `.heygem-jobs/` and `.local/`.

Telemetry uses periodic `nvidia-smi` sampling. `peakSystemMemoryMiB` is **whole-GPU
usage**, not exclusive process allocation; `peakIncreaseMiB` subtracts the initial
whole-GPU baseline. Sampling can miss short peaks, and other programs can move the
baseline. Values are evidence for this test configuration, not guaranteed limits.

Before publishing, the native task must reach service success **2** (not the
Easegen HTTP API's **3**), and its output must be inside the new workspace. The
runner requires both audio and video, finite durations within 0.25 seconds of the
narration, a file different from the input template, and full FFmpeg decoding.
The Plus handoff additionally measures a face-safe zone and checks alignment.

## Measured scope: 2026-09-04

Windows, RTX 2070 **8 GB**, driver **551.78**, system RAM **64 GB**, bundle Python
3.10.16 / ONNX Runtime 1.23.2, FP32 DINet, enhancement off. Private test assets are
not distributed. Input narration 2.051678 s; input template 480×832 at 30 fps.

| Same input, threaded backend | Batch 1 (first run) | Batch 4 (next run) | Batch 1 (warm repeat) |
| --- | ---: | ---: | ---: |
| Whole-GPU baseline | 1086 MiB | 1086 MiB | 1075 MiB |
| Sampled whole-GPU peak | 2941 MiB | 3963 MiB | 2946 MiB |
| Peak minus baseline | 1855 MiB | 2877 MiB | 1871 MiB |
| Wall time, including initialization/validation | 163.02 s | 62.47 s | 28.84 s |
| Output | 2.050998 s, H.264 + AAC, 61 frames | same duration/streams/frames | byte-identical to first batch 1 |

Observed batch-1 peak was 1022 MiB lower (25.8% of the whole-GPU peak, or 35.5%
of baseline-subtracted increase). Both outputs passed full decoding. Their decoded
full-frame SSIM was 0.998261; this is a similarity measurement, **not** proof of
perfect lip sync or a perceptual quality guarantee. Three sampled batch-1 frames
all contained a detectable face.

A final integration smoke called the Plus pipeline's real `generate_presenter`
entrypoint with a directory containing spaces, `&`, `%` and `!`. A 1-second
template successfully drove 2.05 seconds of narration through streaming replay;
audio/video validation and face-safe-zone output passed. This run took 38.02 s,
with a sampled whole-GPU peak of 2948 MiB (baseline 1161 MiB). Its different
template means it is not part of the batch-size comparison above.

These are sequential, single-machine smoke tests, not a statistically controlled
benchmark. The first run has different cache/initialization conditions, so the
wall-time difference cannot be attributed solely to batch size. This compares
batch sizes within the new adapter, **not** the original multi-process bundle.
An earlier multi-process attempt failed with WinError 1455 while importing CUDA
DLLs; it did not provide a valid completed-run baseline.

No 4 GB, 6 GB, long-form 1080p/4K, multi-job, enhancement-on, or CPU-only acceptance
is established by this fixture. 8 GB is a **tested configuration**, not a measured
minimum. The short test validates the digital-human stage; it does not revalidate
IndexTTS2, alignment or a complete Remotion render.
