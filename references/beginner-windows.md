# Windows 新手：从下载到自己的数字人口播视频

适用 Codex、WorkBuddy 或其他能读取本地文件、执行终端命令的 Agent。
各工具的 Skill 安装入口可能不同；不能自动识别时，让它读取本仓库 `SKILL.md` 和本指南即可。
**安装 Skill 不等于安装了配音模型和数字人引擎。首次需要联网下载，生成阶段在本机运行，不租远程 GPU。**

## 1. 电脑要求

- Windows x64 + NVIDIA CUDA 显卡及兼容驱动，不使用 WSL、Docker、Redis、对象存储。
- 已实测 RTX 2070 8GB 的短片数字人合成；4GB/6GB 未验证，AMD/Intel 核显、纯 CPU 暂不支持该后端。
- IndexTTS2 可单独选择 CPU（慢）或兼容的 CUDA，不代表 HeyGem 也能用 CPU。
- 下载包、解压目录、TTS 权重、每次任务中间文件分别占空间；压缩大小不等于运行所需磁盘空间。
- 先试 3—5 秒口播，不要第一次就提交几分钟长稿。最终 1080P 画布不等于人物源视频必须 1080P。

## 2. 组件从哪里获取

| 组件 | 用途与获取方式 |
| --- | --- |
| 本 Skill | [GitHub 仓库](https://github.com/haojing8312/easegen-video-talkcraft)，克隆或 Download ZIP 后解压 |
| Git / Python / uv | [Git](https://git-scm.com/downloads/win)、[Python](https://www.python.org/downloads/windows/)、[uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/)；本指南工具环境使用 Python 3.10 |
| IndexTTS2 | 官方 [index-tts/index-tts](https://github.com/index-tts/index-tts) 配音，模型选 **IndexTeam/IndexTTS-2**；具体安装命令见第 4 节 |
| 数字人运行包 | 联系 **Easegen 维护者**，扫码 [Easegen 作者微信](../assets/easegen-author-wechat.png)，备注“easegen 数字人运行包”；也可在[本仓库 Issues](https://github.com/haojing8312/easegen-video-talkcraft/issues)询问入口。不是上游 video-talkcraft 作者或讨论群 |
| FFmpeg / FFprobe | 数字人包 `engine/py39/ffmpeg/bin` 提供，用于转换、检测和合成；单独获取见 [FFmpeg 官方下载页](https://ffmpeg.org/download.html)的 Windows 构建链接 |
| 字幕对齐 | 新手先装 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，首跑自动下载模型；可换 [FireRed 模型](https://huggingface.co/csukuangfj2/sherpa-onnx-fire-red-asr2-ctc-zh_en-int8-2026-02-25) |
| Node.js / Remotion / 浏览器 | [Node.js](https://nodejs.org/en/download) 选受支持的 LTS；Agent 按 [Remotion 文档](https://www.remotion.dev/docs/)为单片工程安装依赖和渲染浏览器 |
| OpenCV / YuNet | 工具环境安装 `opencv-python`；`face_bbox.py` 首次下载 [OpenCV 官方 YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)，测量人脸，避免字幕挡脸 |

数字人包独立交付，可通过百度网盘下载；**公开网盘链接和提取码尚未配置，先联系 Easegen 维护者获取，勿使用猜测链接。**
核对包名、版本、SHA256 和适配后端 `heygem-win-onnx`。包内包含数字人环境与模型，不包含私人声音、人物素材，也不包含 IndexTTS2。
当前 1.0.0 运行包约 **8.06 GB**，解压约 **12.01 GiB**，还需为任务文件和其他组件预留空间；[校验值与验收记录](runtime-distribution.md#100-本机迁移验收2026-09-07)。
付费部署服务与第三方商业许可分开说明。自行改造可看 [Duix-Avatar 官方仓库](https://github.com/duixcom/Duix-Avatar)，但它不是运行包的直接替代，接入契约见 [Plus 文档](plus-pipeline.md)。

## 3. 素材放哪里

`D:\Easegen` 是推荐位置，可以换磁盘；改后让 Agent 同步修改命令中的路径。
解压后，以**同时能看到 `check.cmd` 和 `engine` 文件夹的那一层**作为运行包根目录，避免双层解压后指错位置。

```text
D:\Easegen\
├── easegen-video-talkcraft\       # Skill，有 SKILL.md
│   └── .venv-tools\              # 编排、字幕、人脸检查的独立 Python
├── index-tts\                    # 官方代码，自己的 .venv
│   ├── .venv\
│   └── checkpoints_2\            # IndexTTS-2 主模型及辅助模型
├── avatar-runtime\               # 数字人包最外层文件夹，可改成此名
│   ├── check.cmd
│   ├── render.cmd
│   ├── avatar_runtime.py
│   ├── engine\                  # --dh-engine-root 指向这里！
│   │   ├── py39\python.exe      # 实际 Python 3.10.16，不要随意升级
│   │   └── ...                  # 模型、原生模块、依赖
│   └── adapter\
└── projects\my-first-video\
    └── source\                  # 你只需先准备这里三个文件
        ├── script.txt
        ├── voice-reference.wav
        └── avatar.mp4
```

不要把素材放入权重目录或 Skill 的 `assets/`。`source/` 是推荐约定，不是引擎写死的要求。
`init` 记录路径，`run` 将素材复制到项目 `input/`，不会删除原文件。

### 三个文件分别是什么

| 文件 | 要求与建议 |
| --- | --- |
| `script.txt` | UTF-8 纯文本口播稿，一句一行，不带 Markdown 标题、镜头备注；数字按希望念出的方式写清楚 |
| `voice-reference.wav` | 本人或授权的 **5—15 秒干净说话录音**作为起点；单人、无音乐、无回声、无爆音。建议 PCM WAV、单声道；24kHz 可作统一整理规格，不是唯一支持采样率。不要把 MP3 改扩展名冒充 WAV |
| `avatar.mp4` | 本人或授权的**单人视频，不是照片**；脸和嘴清晰、正脸或轻微侧脸、光线稳定、无遮挡、无切镜、无字幕贴在嘴上。建议自然讲话、动作较小、固定机位；10—30 秒作为初始素材建议。短于配音会循环，过短可能明显重复动作 |

先用接近已测 `480×832 / 30fps` 的短人物素材验证，再提高规格；长片、高分辨率和大幅转头不在已有短片验收范围内。
人物视频原声不必与新稿一致，最终口播来自生成配音。声音与人物可以不同，但均须获得授权。
**参考音色不等于完整配音**：前者告诉 IndexTTS2“用谁的声音”，后者才是数字人模块要读的整段内容。

## 4. 安装官方 IndexTTS2

本 Skill 不修改 IndexTTS2 模型或推理源码，而是调用官方 `indextts2 synth` / `python -m indextts.cli_v2`。
依据：[官方 CLI](https://github.com/index-tts/index-tts/blob/main/indextts/cli_v2.py)、[官方安装说明](https://github.com/index-tts/index-tts#-getting-started)。
2026-09-07 核对官方 HEAD：`ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c`；这是接口核对版本，不是本项目全流程实测版本承诺。
官方现在也有 2.5，**此处选择 IndexTTS-2，不要把 2.5 权重填给 v2 CLI**。

安装 Git、Python、uv 后，在 PowerShell 执行（Agent 可以代执行）：

```powershell
New-Item -ItemType Directory -Force D:\Easegen | Out-Null
Set-Location D:\Easegen
git clone https://github.com/index-tts/index-tts.git
Set-Location D:\Easegen\index-tts
uv sync --extra webui
uv run python -m indextts.cli_v2 --help
uv run python -m indextts.cli_v2 download --source modelscope --model-dir D:\Easegen\index-tts\checkpoints_2
uv run python -m indextts.cli_v2 check --model-dir D:\Easegen\index-tts\checkpoints_2 --device cpu
```

也可将 `--source modelscope` 换成 `--source huggingface`。官方 v2 `download` 准备主模型和辅助模型，只下载几个 `.pth` 可能缺资源。
Windows 先不装 DeepSpeed/额外加速扩展，所以不用 `--all-extras`。安装失败先检查官方对应版本的 Python、PyTorch、驱动要求；数字人 CUDA 环境不等于 TTS 环境。
`check` 是依赖检查，下一步必须实际合成试听：

```powershell
uv run python -m indextts.cli_v2 synth `
  --text "你好，这是我的第一条数字人测试视频。" `
  --voice D:\Easegen\projects\my-first-video\source\voice-reference.wav `
  --output D:\Easegen\projects\my-first-video\tts-test.wav `
  --model-dir D:\Easegen\index-tts\checkpoints_2 `
  --device cpu --no-fp16 --no-deepspeed --no-cuda-kernel
```

CPU 较慢；兼容 NVIDIA 环境可改 `--device cuda:0`。首次成功后记录 `git rev-parse HEAD`，不要无提示升级依赖。
已有官方环境直接传 Python 和模型路径，不必重复安装，也不需要 `easegen-core` 或 `indextts2-api` 服务。

## 5. 单独测试数字人

解压到 `D:\Easegen\avatar-runtime`，双击 `check.cmd`。真实生成二选一：

- 无命令行：将**完整配音**复制为运行包 `input\audio.wav`，人物视频放 `input\avatar.mp4`，双击 `render.cmd`；缺目录时新建。结果在 `output\host.mp4`。
- 保持素材原位置：使用以下 PowerShell 命令。

```powershell
Set-Location D:\Easegen\avatar-runtime
.\engine\py39\python.exe -B -s .\avatar_runtime.py render `
  --audio D:\Easegen\projects\my-first-video\tts-test.wav `
  --avatar D:\Easegen\projects\my-first-video\source\avatar.mp4 `
  --output D:\Easegen\projects\my-first-video\avatar-test.mp4
```

检查声音、口型是否跟随新配音、末尾是否完整。已有输出不会被静默覆盖；换新输出名再试。
`check` 不代表模型实际使用 CUDA，真实渲染才能验证。日志在输出旁 `.heygem-jobs/`，不要公开上传整个日志目录。

## 6. 安装工具环境并串起 Plus

已有 Skill 文件夹就跳过克隆。在 PowerShell：

```powershell
Set-Location D:\Easegen
git clone https://github.com/haojing8312/easegen-video-talkcraft.git
Set-Location D:\Easegen\easegen-video-talkcraft
py -3.10 -m venv .venv-tools
.\.venv-tools\Scripts\python.exe -m pip install zhconv pypinyin soundfile numpy faster-whisper opencv-python pillow
$env:PATH = "D:\Easegen\avatar-runtime\engine\py39\ffmpeg\bin;" + $env:PATH
ffmpeg -version
ffprobe -version
node --version
npm --version
```

PATH 只在当前 PowerShell 生效；新终端重新设置，或让 Agent 每次调用时设置。
**不要给数字人 Python 安装/升级这些工具依赖。** Remotion 依赖和浏览器由 Agent 在单片工程内配置，仓库根目录的 `npm install` 不是完整成片工程安装。
从 Skill 根目录初始化并运行（同一 PowerShell）：

```powershell
.\.venv-tools\Scripts\python.exe scripts\plus_pipeline.py init `
  --project-dir D:\Easegen\projects\my-first-video `
  --script-file D:\Easegen\projects\my-first-video\source\script.txt `
  --voice-reference D:\Easegen\projects\my-first-video\source\voice-reference.wav `
  --avatar-video D:\Easegen\projects\my-first-video\source\avatar.mp4 `
  --indextts-python D:\Easegen\index-tts\.venv\Scripts\python.exe `
  --tts-model-dir D:\Easegen\index-tts\checkpoints_2 `
  --tts-device cpu --alignment-backend whisper `
  --dh-backend heygem-win-onnx `
  --dh-engine-root D:\Easegen\avatar-runtime\engine `
  --dh-batch-size 1 --width 1920 --height 1080
.\.venv-tools\Scripts\python.exe scripts\plus_pipeline.py plan --project-dir D:\Easegen\projects\my-first-video
.\.venv-tools\Scripts\python.exe scripts\plus_pipeline.py preflight --project-dir D:\Easegen\projects\my-first-video
.\.venv-tools\Scripts\python.exe scripts\plus_pipeline.py run --project-dir D:\Easegen\projects\my-first-video
```

已初始化不要重复 `init`，参数在 `plus-manifest.json`，让 Agent 检查后修改；新作品换项目目录。
`preflight` 不是全依赖安装器，不能替代实际合成检查。`--offline` 只跳过部分探测，不保证后续生成不下载模型。
中文对齐可改装 `sherpa-onnx`，将上表 FireRed 的 `model.int8.onnx`、`tokens.txt` 放同一文件夹，初始化改用 `--alignment-backend firered --alignment-model-dir <模型文件夹>`。

成功后有 `audio/full.wav`、`audio/timestamps.json`、`presenter/host.mp4`、`presenter/face-zone.json`、`talkcraft-input.json`、`run-state.json`。
**这还不是带包装的最终成片。** 让 Agent 按 `SKILL.md` 继续读取 `talkcraft-input.json`，完成 SHOTBOOK、Remotion、字幕动效、渲染和验收，最终 MP4 写到项目 `final/` 并告知实际路径。

## 7. 复制给 Codex / WorkBuddy 的提示词

首次安装与生成：

```text
请读取 D:\Easegen\easegen-video-talkcraft\SKILL.md 和 references\beginner-windows.md，使用 easegen-video-talkcraft。
先检查本地依赖并按指南配置。数字人包已解压到 D:\Easegen\avatar-runtime。
IndexTTS2 使用官方版本，代码在 D:\Easegen\index-tts，模型在 checkpoints_2。
稿子、参考声音、人物视频位于 D:\Easegen\projects\my-first-video\source。
先用短片验证配音和口型，再生成横屏 1080P、带字幕的完整视频，放项目 final 文件夹。
全部本机推理，不租 GPU、不上传素材、不修改原稿；缺运行包或素材时告诉我缺什么。
不要停在 talkcraft-input.json，继续完成分镜、Remotion 渲染和验收，告诉我成片路径。
```

以后沿用已验证环境和素材：

```text
使用 easegen-video-talkcraft，沿用上次已验证的本地环境、音色和人物素材。
把下面口播稿生成带字幕的横屏 1080P 数字人口播视频，保存到新项目，不覆盖上次作品。
口播稿：【粘贴稿子】
```

Agent 软件本身可能使用联网模型；“本地推理”指本项目的 TTS、数字人和渲染。
不要上传音色/人物素材到外部服务；敏感稿件还需核对所用 Agent 产品的数据处理设置。

## 8. 常见问题

| 现象 | 先检查什么 |
| --- | --- |
| `No module named indextts.cli_v2` | 是否使用官方 IndexTTS2 `.venv` 的 Python，版本是否包含 CLI，而不是数字人 Python |
| 缺 `hf_cache` / 模型 | 用官方 v2 CLI `download` 补全辅助模型，不只下载主权重 |
| 找不到 Python / 原生模块 | 是否完整解压、是否误指向上层目录；实际引擎是运行包的 `engine` |
| 找不到 `ffprobe` | 当前 Agent 终端 PATH 添加 `engine/py39/ffmpeg/bin` |
| 缺 DLL / CUDA Provider 加载失败 | 检查驱动、完整解压、使用包内 Python；不要随意升级包内依赖或复制 DLL 到 System32 |
| 显存不足 | 一次只跑一项任务，batch=1、增强关闭、TTS 改 CPU；4GB 不保证可用 |
| 对齐失败 | 检查配音截断/漏字、稿件与音频是否一致；不要跳过验收冒充成功 |
| 只有人物，没有字幕动效 | Plus 只准备中间素材，让 Agent 继续处理 `talkcraft-input.json` 并渲染 |
| 想离线使用 | 先下载依赖、所有模型、YuNet 和渲染浏览器，再断网实测全流程 |

反馈提供系统、显卡/驱动、运行包版本、失败阶段、脱敏错误摘要，不要上传整个私人项目。
