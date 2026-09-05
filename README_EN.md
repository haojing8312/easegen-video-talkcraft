<div align="center">

<img src="assets/logo.svg" alt="easegen-video-talkcraft logo" width="150">

<h1>easegen-video-talkcraft</h1>

[![Gallery](https://img.shields.io/badge/Gallery-live%20previews-7A5AF8)](https://vincentwei1021.github.io/video-talkcraft/)
[![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial-blue)](LICENSE)

**A local-first digital-human video Skill: IndexTTS2 · local avatar runtimes · 79 motion cards · Remotion · triple-gate QA**

[中文](README.md) | [English](README_EN.md)

</div>

**easegen-video-talkcraft** is an Easegen-enhanced distribution of
[Vincentwei1021/video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft).
It preserves the upstream 79 motion cards, SHOTBOOK system, workbench, and QA gates,
while adding a local-first Plus pipeline that can turn a script, an authorized
voice reference, and avatar footage into IndexTTS2 narration and locally generated
presenter footage before rendering with [Remotion](https://www.remotion.dev/).

> This repository does not bundle model weights, CUDA environments, third-party native binaries,
> private voices, or avatar assets, and it has no automatic remote-GPU fallback. Upstream code
> remains under PolyForm Noncommercial 1.0.0; commercial use requires upstream authorization.

![easegen-video-talkcraft: fully local, from narration script to a high-quality digital-human video](assets/easegen-video-talkcraft-cover-v2.png)

## 🙏 Special thanks to video-talkcraft

This project is built on Vincent Wei's
**[video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)**.
We sincerely thank Vincent Wei and the upstream contributors for the narration-video workflow,
79 motion recipe cards, SHOTBOOK cinematography system, Remotion templates, motion workbench,
and machine-verifiable QA methodology. Easegen Plus adds IndexTTS2 and local digital-human
integration on top of that foundation.

If this project helps you, please also follow and support the upstream author:
**[GitHub · Vincentwei1021/video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)**.

> The methodology docs and recipe cards are written in Chinese — the toolkit is
> built Chinese-narration-first (mixed Chinese/English narration is fully
> supported). Agents read them natively.

🖼️ [**Browse all 79 motion previews in the live Gallery »**](https://vincentwei1021.github.io/video-talkcraft/)

[![video-talkcraft live gallery](assets/gallery-en.png)](https://vincentwei1021.github.io/video-talkcraft/)

## ✨ Easegen Plus additions

- Local IndexTTS2 narration on CPU/CUDA and other devices supported upstream.
- Native Windows `heygem-win-onnx` (no WSL), Linux `heygem-local`, HeyGem API compatibility,
  and an experimental DH_live CPU path.
- A standalone adapter that keeps model runtimes isolated from Easegen's production
  Redis, API, object-storage, and scheduler code.
- Deterministic artifacts and acceptance checks for audio, presenter video, timing,
  face-safe zones, and the TalkCraft handoff.

See [the Plus pipeline reference](references/plus-pipeline.md) for setup and honest hardware boundaries.
The [native Windows guide](references/windows-onnx.md) documents batch-1 defaults,
threaded workers, isolated outputs, measured VRAM and limitations; CUDA is still required.

## 🧩 Obtaining a HeyGem / avatar runtime

The HeyGem runtime and model files are too large to commit to this repository. Choose one of these paths:

1. **Contact the Easegen maintainer**: scan the WeChat QR code below and include `easegen` in the request to discuss paid deployment, environment setup,
   low-VRAM adaptation, or an independently delivered runtime package where redistribution is authorized.
   The paid service covers installation and integration; third-party model, image, and commercial-use rights
   remain governed by their own licenses and authorization documents.
2. **Build from the official project**: clone
   **[duixcom/Duix-Avatar](https://github.com/duixcom/Duix-Avatar)**, follow its Docker/model setup,
   and either add an Easegen compatibility layer that maps the official `/easy/submit` and `/easy/query`
   endpoints to `/api/v1/easedh/task/create` and `/api/v1/easedh/task/result`, or adapt a local inference
   entrypoint to the `EASEGEN_RESULT_JSON` contract used by `heygem-local`.

> The official checkout cannot be used directly as `--dh-engine-root`, and its port `8383` cannot be
> passed directly as the current `--dh-api-base`; both paths require the documented contract adaptation.

In both cases, review the current HeyGem/Duix code, model, Docker-image, redistribution, and commercial-use terms.

<p align="center">
  <img src="assets/easegen-author-wechat.png" alt="Easegen maintainer WeChat QR code" width="280">
  <br>
  <sub>Project collaboration and technical discussion: include easegen in your WeChat request</sub>
</p>

## 🆕 What's new

**2026-09-02**

- **Motion workbench `workbench/`** — a CapCut-style post-production desk for finished videos: multi-track timeline,
  library (media / motion cards / SFX / backgrounds), schema-driven inspector, live preview and one-click **Export**.
  All 79 motion cards are parameterized (copy, colors, sizes, positions editable; timing vitals stay fixed).
  A narration video can be split into seven kinds of editable units — subtitles / transitions / environment /
  avatar / shots / voiceover / SFX. The skill opens it for you after delivery. → [**Illustrated guide (zh)**](workbench/GUIDE.md)

  <a href="workbench/GUIDE.md"><img src="workbench/docs/img/01-overview.png" alt="Workbench overview" width="720"></a>

- **Faster renders: shot-segmented master rendering** — `scripts/render_shots.mjs` renders per-shot segments in
  parallel (single-process inside each segment to keep rasterization consistent), then concatenates, mixes in the
  full audio track and asserts frame counts; changing one shot re-renders only that segment ± neighbours.
  `scripts/render_stills.mjs` renders batches of stills from a single bundle.
- **Fewer review tokens** — `scripts/contact_sheet.py` tiles QA frames into 3×4 sheets for the reviewer subagent;
  burst triples are extracted only at anchors flagged `"burst": true` (they used to be 2/3 of the review material).
- **One review round, then deliver** — after the machine gates pass, a single independent review round fixes
  P0/P1 and the video ships; further rounds are opt-in (3 max) instead of "loop until clean".

| Measured (201 s vertical video) | Before | Now |
|---|---|---|
| Full first render | 13 min | 9 min |
| New video with audio after changing one shot | full re-render | 53 s |
| 43 sampled stills | 11 min | ~1 min |
| Reviewer reading 160 QA frames | ≈160k tokens / 21 min | ≈40k tokens / 7 min (sheets) |

- New card: community-contributed **douyin-follow-card** ([@scpcn01vision-oss](https://github.com/scpcn01vision-oss)) — 79 cards total.

## ✨ Highlights

- **Word-level voiceover sync** — `scripts/timestamps_cpu.py` aligns
  your script to the audio (FireRedASR2-CTC int8 by default, faster-whisper as
  the zero-download fallback). Benchmarked against a GPU forced aligner on a
  110s mixed-language narration: median per-character offset 20–40 ms,
  worst case 200 ms, zero false QA flags. Every motion beat anchors to the
  exact word.
- **79 motion recipe cards** — each with intent, parameters, known pitfalls,
  a copy-paste self-contained Remotion tsx source, and a runnable HTML
  preview — browse them all in the
  [online Gallery](https://vincentwei1021.github.io/video-talkcraft/) or
  locally with `open gallery/index.html`. Kinetic type, data shots, evidence
  tours, six motion-carry transitions, a long-take world canvas, host
  compositing, and more.
- **A 7-layer anti-slideshow system** — continuous camera curves, parallax
  planes, idle/yield lifecycle, breathing environment. Statically frozen
  frames are structurally impossible (and automatically detected if they
  slip through).
- **Layout discipline that survives review** — semantic-beat storyboarding,
  on-screen element budgets, whitespace anchors, pivot-sentence cut rules,
  and face safety zones measured by real detection
  (`scripts/face_bbox.py`), not by eye.
- **Triple-gate QA** — automated stillness detection, per-cue SFX energy
  verification on a solo track, and an independent-reviewer pass armed with
  anchor frames (plus burst triples at state-switch anchors, which catch
  time-domain defects single frames can't show).

## 🚀 Quick start

**The most direct way: hand the repo link to your agent.**
In Claude Code / Codex or a similar agent, just say:

```text
Install this skill for me: https://github.com/haojing8312/easegen-video-talkcraft
```

Or install with the [skills](https://skills.sh/) CLI / manually:

```bash
npx skills add haojing8312/easegen-video-talkcraft
```

```bash
git clone https://github.com/haojing8312/easegen-video-talkcraft.git
cd easegen-video-talkcraft
ln -s "$(pwd)" ~/.claude/skills/easegen-video-talkcraft   # Claude Code
# or
ln -s "$(pwd)" ~/.codex/skills/easegen-video-talkcraft    # Codex
```

Environment (the agent will set this up as needed):

- Node 18+ (Remotion render; `npm install` inside the per-video project)
- Python 3.10+ and `pip install zhconv pypinyin sherpa-onnx soundfile numpy`
  for the timestamp pipeline (first use downloads the 767 MB FireRedASR2-CTC
  model once — URLs in `scripts/timestamps_cpu.py`; or use
  `--backend whisper` to skip the manual download)
- ffmpeg

Then make requests like:

```text
Use easegen-video-talkcraft to turn this narration script + voiceover.wav into a video.
Make a 100-second explainer about <topic>; here is the script and the audio.
Use the Plus pipeline to turn this script, voice reference, and avatar clip into a digital-human video.
```

## 🎞 What you bring vs. what it does

| You bring (inputs) | The skill does |
| --- | --- |
| Narration script | Word-level timestamp alignment, with per-sentence QA flags |
| Finished voiceover — any TTS or human recording | SHOTBOOK storyboarding: semantic beats, layer matrices, layout budgets |
| Optional host footage — ordinary video works (keying + face-zone tooling included; green screen keys cleanest) | Remotion implementation on four global systems (camera / parallax / yield / environment), transitions, SFX placement |
| Optional B-roll / screenshots | Render + triple-gate QA (machine gates all green + one independent review round with P0/P1 fixed, then deliver; optional extra rounds, 3 max), loudness-normalized delivery |

## 📦 What's included

| Content | Description |
| --- | --- |
| 79 motion recipe cards | Intent, energy, parameters, implementation notes, and known pitfalls — every card ships a self-contained Remotion tsx source (`template/cards/`, copy one file and go) plus a runnable HTML demo |
| Gallery | [Online](https://vincentwei1021.github.io/video-talkcraft/) or local (`open gallery/index.html`) — browse and autoplay all 79 previews, search by name/keyword |
| Motion systems | CameraRig, parallax planes, idle/yield lifecycle, environment layer, six transitions, long-take world canvas (`template/motion-systems/`) |
| Components | Plain-cut subtitles, flower-word titles, smash words, highlight sweeps, pencil draw, number rolls (`template/components/`) |
| Pipeline scripts | Word-level timestamps (2 ASR backends), face-zone detection, stillness check, SFX presence check, QA frame extraction (`scripts/`) |
| Methodology | Design language (Apple-paradigm default), shot design worksheets, cinematography rules, storyboard format, QA rubrics (`references/`) |
| Embedded SFX | Per-card sound cue tables with real samples embedded in the demo lib (licenses in `demos/_lib/sfx/ATTRIBUTION.md`) |

## 🗂 Repository structure

```text
easegen-video-talkcraft/
├── SKILL.md                    # Agent entry point: the 8-step pipeline and hard rules
├── references/
│   ├── design-language.md      # Default visual system (palette/type/layout/subtitles)
│   ├── shot-design.md          # 3-plane worksheet + 7 shot-type presets
│   ├── cinematography.md       # 7-layer model, transitions, layout budget, QA gates
│   ├── shotbook-example.md     # A full storyboard example
│   ├── cards/                  # 79 motion recipe cards
│   ├── taxonomy.md             # Card index by category and source
│   ├── broll-sources.md        # Attribution-free stock sources (APIs, license traps)
│   ├── host-footage.md         # Host footage: input spec, keying, face safety zone
│   └── demo-spec.md            # Card/demo authoring spec
├── demos/                      # 79 runnable HTML previews (+ shared lib with embedded SFX)
├── gallery/                    # One-page local gallery
├── template/                   # Copy-paste Remotion code
│   ├── cards/                  # Per-card self-contained tsx sources (the skill's primary reference)
│   ├── motion-systems/         # Camera / parallax / yield / environment / transitions / long-take
│   └── components/             # Subtitles, flower words, smash words, pencil, etc.
└── scripts/                    # Timestamps, face bbox, QA tooling
```

For the full workflow, start at [SKILL.md](SKILL.md).

## ❓ FAQ

**What is video-talkcraft?**
An open-source AI agent skill (for Claude Code / Codex) that turns a narration
script plus a finished voiceover into a fully animated, voiceover-driven
explainer video. It is
not an editor and not a template site — the agent reads the methodology, picks
motion recipe cards, writes [Remotion](https://www.remotion.dev/) code, and
runs triple-gate QA to deliver a publish-ready explainer.

**What kinds of videos can it make?**
Landscape, voiceover-driven explainer videos: knowledge explainers, product
reviews, news breakdowns, opinion commentary. Designed Chinese-narration-first; mixed
Chinese/English narration is fully supported.

**What do I need to provide?**
A narration script (text) and a finished voiceover (any TTS or human
recording); host footage and B-roll are optional.

**Is it free?**
Free for personal, educational, and research use (PolyForm Noncommercial
1.0.0), and the videos you produce belong to you; commercial use of the
toolkit itself requires prior authorization (see below).

## 📄 License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, educational, and
research use. **Any commercial use of the toolkit requires prior
authorization** — email
[vincentwei1021@gmail.com](mailto:vincentwei1021@gmail.com) or open
a GitHub issue.

This repository preserves the upstream Git history, Required Notice, and license.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the runtime boundary of
the Easegen additions. Source availability does not grant commercial-use or model-redistribution rights.

**Videos you produce with this skill belong to you.** If it helped, a mention
of the author's accounts in your video description is appreciated — and
entirely optional.

## 🔊 Audio and asset notes

- Embedded SFX samples: sources and licenses in
  [demos/_lib/sfx/ATTRIBUTION.md](demos/_lib/sfx/ATTRIBUTION.md).
- The B-roll sourcing guide only admits attribution-free stock (Pexels,
  Pixabay, Mixkit Free, Coverr, NASA) and documents the license traps of the
  ones it rejects — see
  [references/broll-sources.md](references/broll-sources.md).
- The demo host footage (`demos/_lib/dh-host.webm`) is an AI-generated
  presenter used as a placeholder; replace it with your own host footage in
  production.

## 🙏 Acknowledgements

- **[Remotion](https://www.remotion.dev/)** — the React video framework
  powering every render here (note its own
  [license](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)).
- **[FireRedASR2](https://github.com/FireRedTeam/FireRedASR2S)** via
  **[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** and
  **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — the
  timestamp backends; **Qwen3-ASR/ForcedAligner** served as the benchmarking
  reference.
- **OpenCV YuNet** — the face detector behind the face-safety-zone rule.
- **Pexels · Pixabay · NASA · Mixkit** — attribution-free asset sources.
- **Claude Code** — this library was built, iterated, and QA'd with an AI
  coding agent, using the same review loops the skill teaches.

## Follow me

<p>
  <a href="https://x.com/VincentWei93"><img alt="Follow Vincent on X" src="https://img.shields.io/badge/X-Follow_Me-000000?style=for-the-badge&logo=x&logoColor=white"></a>
  <a href="https://www.douyin.com/user/MS4wLjABAAAAK1pkjBxilk2Oi_9h_vFyD-lTAu9CTlvhmOtkosDvvxg"><img alt="Follow Vincent on Douyin" src="https://img.shields.io/badge/Douyin-Follow_Me-000000?style=for-the-badge&logo=tiktok&logoColor=white"></a>
  <a href="https://xhslink.cn/m/At9iP2d5C1V"><img alt="Follow Vincent on Red Note" src="https://img.shields.io/badge/Red_Note-Follow_Me-FF2442?style=for-the-badge&logo=xiaohongshu&logoColor=white"></a>
</p>
