# Third-party notices

## Upstream foundation

`easegen-video-talkcraft` is derived from
[Vincentwei1021/video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft).
We thank Vincent Wei and the upstream contributors for the core workflow, motion-card library,
SHOTBOOK system, Remotion templates, workbench, and QA methodology. The upstream Required Notice
and PolyForm Noncommercial 1.0.0 terms are preserved in this repository's `LICENSE` file.

## Optional runtime boundary

`easegen-video-talkcraft` orchestrates optional software installed separately by the user. Those runtimes are not included in this Skill and are not relicensed by this repository.

The optional integrations include:

- IndexTTS2 and its model files.
- An external Easegen Digital Human v2 engine directory and its inherited HeyGem-compatible model files and native extensions. The Skill contains only a standalone adapter and does not bundle those files.
- A locally hosted HeyGem API implementation.
- DH_live_mini and its prepared-avatar assets.
- FireRedASR2-CTC or faster-whisper for alignment.
- FFmpeg, Remotion, and their dependencies.

Before redistributing a runtime, model, native library, voice reference, or avatar asset, consult its own license and preserve all required notices. In particular, do not treat availability in a community bundle or download link as permission to redistribute or use commercially.
