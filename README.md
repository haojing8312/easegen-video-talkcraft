<div align="center">

<img src="assets/logo.svg" alt="easegen-video-talkcraft logo" width="150">

<h1>easegen-video-talkcraft</h1>

[![Gallery](https://img.shields.io/badge/Gallery-live%20previews-7A5AF8)](https://vincentwei1021.github.io/video-talkcraft/)
[![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial-blue)](LICENSE)
[![WeChat](https://img.shields.io/badge/WeChat-%E8%AE%A8%E8%AE%BA%E7%BE%A4-07C160?logo=wechat&logoColor=white)](assets/wechat-group.jpg)

**本地数字人口播视频 Skill：IndexTTS2 · 本地数字人 · 108 张动效配方卡 · Remotion · 三重验收**

[中文](README.md) | [English](README_EN.md)

</div>

**easegen-video-talkcraft** 是 [Vincentwei1021/video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)
的 Easegen 增强发行版。它完整保留上游的 108 张动效卡、SHOTBOOK 镜头体系、工作台与三重验收，
新增本地优先的 Plus 管线：从口播稿、授权音色参考和人物母片出发，调用用户独立安装的
IndexTTS2 与本地数字人运行时，再用 [Remotion](https://www.remotion.dev/) 合成可复现成片。

> 本仓库不包含模型权重、CUDA 环境、第三方原生二进制、私人音色或头像素材，也不接入远程 GPU 租赁。
> 上游代码继续遵循 PolyForm Noncommercial 1.0.0，商业使用需取得原作者授权。

第一次使用？先读 **[Windows 新手指南：下载组件 → 放入自己的素材 → 让 Codex / WorkBuddy 生成](references/beginner-windows.md)**。

![easegen-video-talkcraft：完全本地，从口播稿生成高质量数字人成片](assets/easegen-video-talkcraft-cover-v2.png)

## 🙏 特别致谢 video-talkcraft

本项目基于 Vincent Wei 开源的
**[video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)** 构建。
衷心感谢 Vincent Wei 及其社区贡献者提供口播视频工作流、108 张动效配方卡、SHOTBOOK 镜头体系、
Remotion 工程模板、动效工作台和机器验收方法。Easegen Plus 的 IndexTTS2 与本地数字人能力是在这些成果之上扩展完成的。

如果本项目对你有帮助，也请前往上游仓库关注并支持原作者：
**[GitHub · Vincentwei1021/video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)**。

🖼️ [**在线画廊：108 张动效预览一页全览 »**](https://vincentwei1021.github.io/video-talkcraft/)

[![video-talkcraft 在线画廊](assets/gallery-zh.png)](https://vincentwei1021.github.io/video-talkcraft/)

## ✨ Easegen Plus 新增能力

- **IndexTTS2 本地配音**：支持 CPU/CUDA 等上游设备；CPU 可运行但不承诺实时速度。
- **本地数字人后端**：Windows 原生 `heygem-win-onnx`，不使用 WSL；Linux 使用 `heygem-local`。兼容 HeyGem API，保留实验性 DH_live CPU 路径。
- **Windows 低显存适配**：batch=1、可关闭人脸增强、单进程线程工作器、有界流式读帧、任务目录隔离与超时进程树回收。仍需 NVIDIA GPU，详见 [原生运行与实测说明](references/windows-onnx.md)。
- **独立运行边界**：Skill 自带 standalone 适配层，模型与生产版 `easegen-digitalhuman-v2` 保持隔离。
- **可复现交付**：固定输出配音、数字人、时间戳、人物安全区、运行状态和 TalkCraft 输入清单。

详细配置与验收边界见 [Plus 管线文档](references/plus-pipeline.md)。

## 🖥️ 显存要求：4GB 显卡能运行吗？

**目前已验证的显卡是 NVIDIA RTX 2070 8GB；已有 4GB 显卡用户反馈显存不足，6GB 尚未完成实机验收，最低显存要求仍未确定。**
这不代表模型必须占用 8GB，也不能据此承诺“最低 4GB 即可运行”。以下仅针对 Windows 原生 `heygem-win-onnx` 数字人后端：

| 显卡配置 | 当前验证状态 |
| --- | --- |
| NVIDIA RTX 2070 8GB | 已完成短片合成及音视频验收；其他型号仍需核对运行时兼容性。 |
| NVIDIA 4GB | 已有用户反馈显存不足，当前不声明支持。 |
| NVIDIA 6GB | 尚未完成实机验收，不能保证成功。 |
| 无 NVIDIA CUDA 显卡 / 纯 CPU | 当前不支持此 HeyGem 后端；纯 CPU 数字人仍是后续研究方向。 |

实测条件：**batch=1、关闭 GFPGAN 人脸增强、FP32 模型、480×832 / 30fps、约 2.05 秒口播**，
整卡显存采样峰值为 **2941–2948 MiB（约 2.88 GiB）**，包含桌面及其他程序占用。
“8GB 卡上测得约 3GB 峰值”不等于“4GB 卡已验证可用”；显卡型号、驱动、分辨率、增强选项及其他程序都会影响结果。

低显存试运行时使用 `--dh-batch-size 1`，不要开启 `--dh-face-enhancement`，一次只运行一个生成任务，
并先使用短片验证。IndexTTS2 可选择 `--tts-device cpu`，但会更慢；上述显存数据**仅覆盖数字人阶段**，
不是 IndexTTS2 + 数字人 + Remotion 全流程的最低配置承诺，也不是长片或 1080p/4K 的验收结果。
完整环境与实测记录见 [Windows 原生运行说明](references/windows-onnx.md)。

## 🧩 获取 HeyGem / 数字人运行时

HeyGem 运行时和模型体积较大，因此不会直接提交到本仓库。你可以选择：

1. **联系 Easegen 维护者**：扫码添加作者微信（请备注 `easegen`），咨询付费部署、环境配置、低显存适配或经授权的独立运行包。
   付费内容是安装与适配服务；第三方模型、镜像和商业授权仍以各自许可证及授权文件为准。
2. **自行部署官方版本**：从 **[duixcom/Duix-Avatar](https://github.com/duixcom/Duix-Avatar)**
   拉取源码，按官方文档准备 Docker/模型环境，再选择以下一种接入方式：
   - 在官方 `/easy/submit`、`/easy/query` API 前增加 Easegen 兼容层，转换为
     `/api/v1/easedh/task/create`、`/api/v1/easedh/task/result` 契约，再使用 `heygem-api`；
   - 按 `EASEGEN_RESULT_JSON` 契约改造本地推理入口，然后使用 `heygem-local` 适配层。

> 官方仓库不能直接作为 `--dh-engine-root` 使用，官方 `8383` 端口也不能直接填入当前
> `--dh-api-base`；两条路径都需要按上述契约完成适配。

无论选择哪种方式，都必须自行核对 HeyGem/Duix 的代码、模型、Docker 镜像与商业使用条款。

维护者的清理、构建、验收及网盘发布步骤见 [数字人运行包分发说明](references/runtime-distribution.md)。

<p align="center">
  <img src="assets/easegen-author-wechat.png" alt="Easegen 作者微信二维码" width="280">
  <br>
  <sub>项目合作与技术交流：添加微信时请备注 easegen</sub>
</p>

## 统一依赖（runtime/）

所有口播工程的 `remotion/node_modules` 与 `workbench/node_modules` 都指向 `runtime/node_modules`，版本只在 `runtime/package.json` 钉一处（`@remotion/*` 全家同号）。
- 新片开工：Linux/macOS 用 `bash runtime/check-runtime.sh --upgrade`；Windows 用 `node runtime/windows-runtime.mjs check --upgrade`（原生 Node，不使用 WSL）。会装依赖 + 共享无头浏览器、接工作台；新版升级后冒烟，失败回滚。
- 接工程：Linux/macOS 用 `bash runtime/link-runtime.sh <工程根>`；Windows 用 `node runtime/windows-runtime.mjs link <工程根>`（junction + package.json 版本对齐）。工程目录里不跑 `npm install`。
- 一份 `node_modules` ≈ 760 MB（含 190 MB 无头浏览器）；之前每支片各装一份，六个工程 3.9 GB。

## 🆕 更新（What's new）
<!-- 写法约定：每条一句话、≤ 200 字（含指向链接），只写"是什么 + 改了什么行为"；细节、参数、卡名清单一律 → 指向 references / SKILL.md 章节，不在这里展开；中英同步。口径由 2026-09-05 PR #12 定，#14/#18 曾回到长段落，2026-09-07 收回。 -->

**2026-09-11**

- ✂️ **配音预剪 `scripts/voice_trim.py`**——真人录音先以口播稿为真值剪掉口水词 / 结巴重说 / 过长停顿再做时间戳（只剪稿子里没有的插入段，ASR 听错的字永不剪），词表来源可选 FireRed ASR / 逐字 SRT / 词级 JSON，切点吸附帧网格、同一 EDL 可剪人物视频保音画同长（→ SKILL.md ②-0）。
- 🫥 **工作台右键导出透明通道**——时间轨上右键任一动效片段可导出只含这一段的透明视频（MOV ProRes 4444 / WebM VP9 alpha），根底透明、自动去掉卡根层幕底与人物剪影占位，给剪映 / PR / AE 当叠加素材；右键菜单同时带分割 / 复制 / 删除（→ `workbench/GUIDE.md` ⑦）。
- 📺 **工作台实时看板（L1）**——⑤-1 骨架搭完就接入并开着工作台：阶段栏 + 进度轨（每镜 占位 / 已实现 / 已渲 / 已过闸 / 过期 / 红点）+ 镜头视图（单镜预览 · issues · SHOTBOOK 段落）+ 实时成片卡，状态按盘上产物自动推、`scripts/pipeline_state.mjs --pass/--issue` 只补人工判定，代码半成品不再盖页（→ SKILL.md ⑤-2、`workbench/docs/live-pipeline.md`）。
- 🔗 **工作台接入加固**——`kbsrc` 改按真实路径解析、契约模块缺哪个只回退哪个 stub、导出形态差异由 `src/kb/` 适配层归一：接入 skill 正式工程（`Main.tsx` + `scenes/`，无 promo 模块）不再整页 500，「拆解导入」按钮按契约自动禁用（→ `workbench/README.md`「接入口播成片工程」）。

**2026-09-09**

- 🎬 **首镜先做先确认**——⑤ 实现改为先搭全合成骨架、其余镜头占位，只做样板镜并用 `--seg-audio` 出一条有声单镜预览给用户确认，确认后再做其余镜头；⑥-1.5 只剩"整片还是逐镜"一问（→ SKILL.md ⑤-1）。

**2026-09-07**

- ✏️ **G5 线稿示意图系统**——纯文字镜必配一张图标 + 方框 + 箭头的线稿陪衬图，文字不裸放、每句至少一个可见变化，缺陪衬行 preflight 报 WARN（→ `template/motion-systems/schematic.tsx`、`references/schematic.md`）。
- 🎞️ **视频容器边框八式 + 章节主题层**——单视频镜头必须包一式主题边框（浏览器窗 / 胶片 / 拍立得 / 图纸等八式，一片一式、不做假播放器），章节卡按章换色 + 线稿 motif（→ `template/components/theme-frame.tsx`、design-language §1.3）。

**2026-09-05**

- 🔁 **19 张 video-shotcraft 移植卡（89 → 108）**——从姊妹库 [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) 两轮筛选移植（09-06 删定格圈注余 18），tsx 改成本库自包含契约、带母本溯源（→ `references/taxonomy.md` 第八批◎）。
- 🎨 **领域定风格 · 中性卡蒙皮**——开工先由口播稿判定领域、派生风格档写进 SHOTBOOK G0；库里的卡是中性 UI，进片按风格档改皮不改运动命门，每镜写蒙皮行（→ `references/design-language.md` §0）。
- 🧩 **10 张多素材同屏新卡（79 → 89）**——并列句排版、三联画接力、对比分屏、传送带、卡堆扇开、照片墙推轨 / 时间线照片带等，每卡标注输入类型与常用场景，选卡先按素材类型过滤（→ `references/taxonomy.md` 输入类型索引）。
- 📐 **排版规范 `references/layout.md`**——12 栏栅格、间距令牌、字阶最小档、包围盒不相交等九项自检，选中卡的「已知坑 / 落位自检」必须抄进 SHOTBOOK。
- 🎨 **12 款动态幕底入库**——`template/motion-systems/backdrop.tsx` 深浅各 6 款、frame 驱动零随机，默认幕底改为浅 `pastel-mesh-flow` / 深 `mesh-flow-dark`。

**2026-09-04**

- 🎥 **运动系统做减法**——每场景只保留一条极缓推拉相机曲线 + 让位，idle 微动 / 环境呼吸 / 脉冲全部默认关闭。
- 🌐 **网页拍摄不贴图**——网页素材不再静态贴屏，改为镜头滚动 / 巡游 / 放大镜 / 划重点"拍"出来，坐标全吃 Playwright 实测（→ SKILL.md §③、`references/shot-design.md` §2④）。

**2026-09-02**

- 🎛️ **动效工作台 `workbench/`**——剪映式的成片后期台：多轨时间线 + 素材库（素材 / 动效库 / 音效 / 背景）+
  schema 属性面板 + 实时预览 + 一键「导出成片」。108 张动效卡 100% 参数化（文案 / 颜色 / 字号 / 位置可调，
  节奏命门固定不暴露）；口播成片可一键拆成字幕 / 转场 / 环境 / 数字人 / 镜头 / 配音 / 音效七类多轨单元逐项微调。
  skill 交付成片后会主动打开它。→ [**图文指南 workbench/GUIDE.md**](workbench/GUIDE.md)

  <a href="workbench/GUIDE.md"><img src="workbench/docs/img/01-overview.png" alt="动效工作台总览" width="720"></a>

- ⚡ **渲染提速：分段渲染母版制**——`scripts/render_shots.mjs` 按镜头切段并行渲、段内单进程保光栅一致，
  拼装 + 整条音轨混入 + 帧数断言；改一个镜头只重渲该段±邻段。`scripts/render_stills.mjs` 一次 bundle 批量出静帧。
- 🧮 **评审 token 减量**——`scripts/contact_sheet.py` 把 QA 帧拼成 3×4 网格给评审子代理整版浏览；连拍三帧对只对标了
  `"burst": true` 的状态切换锚点抽（曾占评审材料 2/3）。
- ✅ **一轮审片即交付**——机器闸全过后只做 1 轮独立审片、修完 P0/P1 即交付，再询问是否续审（累计封顶 3 轮），
  替代旧的"循环到全过"。

| 实测（201s 竖屏片） | 之前 | 现在 |
|---|---|---|
| 全片首渲 | 13 min | 9 min |
| 改一个镜头出有声新片 | 整渲 | 53 s |
| 43 张静帧抽样 | 11 min | ~1 min |
| 评审读 160 张 QA 帧 | ≈16 万 token / 21 min | ≈4 万 token / 7 min（拼图） |

- 🤝 新卡：社区贡献 **douyin-follow-card 抖音主页关注卡**（[@scpcn01vision-oss](https://github.com/scpcn01vision-oss)），库存 79 张。

## ✨ 亮点

- **字级配音同步**——`scripts/timestamps_cpu.py` 把口播稿对齐到音频
  （默认 FireRedASR2-CTC int8，备选 faster-whisper 免手动下载）。110s 中英混合口播
  对照 GPU 强制对齐器实测：字级偏差中位 20–40ms、最差 200ms、质检零误报。
  每个动效节拍都锚在确切的字上。
- **108 张动效配方卡**——每张有意图、参数、已知坑、可直接复制的自包含 Remotion tsx 源码和可跑的 HTML 预览，
  [在线画廊](https://vincentwei1021.github.io/video-talkcraft/)一页全览
  （本地 `open gallery/index.html` 同款）。动态字卡、数据镜头、证据巡游、
  六式运动承接转场、长镜头世界画布、人物合成等。
- **七层反 PPT 系统**——每场景一条极缓推进 / 拉出的相机曲线 + 让位生命周期 + 六式运动承接转场
  （2026-09-04 起做减法：不再要求主体 idle 与环境呼吸）。
  静止帧在结构上不可能出现（漏网的也会被自动检测抓住）。
- **经得住审片的排版纪律**——语义拍分镜、同屏元素预算、留白锚、枢轴句切镜规则、
  用真实检测（`scripts/face_bbox.py`）量出来的人脸安全区，不靠目测。
- **三重验收**——画面健康双判定（静止段 + 并发光栅抖动，时域缺陷机器抓）、
  纯音效轨逐 cue 能量验证、带动效锚点帧与评审拼图的独立评审。

## 🚀 快速开始

**第一次使用、只有口播稿的用户，先看 [Windows 零基础安装与素材指南](references/beginner-windows.md)。**
安装 Skill 不会自动获得数字人引擎与配音模型。Codex / WorkBuddy 可以按指南配置；
没有自动识别 Skill 时，请让它直接读取本仓库 `SKILL.md` 和该指南。

| 你需要准备 | 从哪里获得 / 放哪里 |
| --- | --- |
| IndexTTS2 配音 | [官方仓库](https://github.com/index-tts/index-tts)，无需 Easegen 定制版；选 **IndexTTS-2**，独立环境安装，[下载命令](references/beginner-windows.md#4-安装官方-indextts2) |
| 数字人运行包 | 联系 **Easegen 维护者**，扫码上方“Easegen 作者微信”，备注“easegen 数字人运行包”；或[本仓库 Issues](https://github.com/haojing8312/easegen-video-talkcraft/issues)。独立交付，可通过百度网盘获取；公开链接尚未配置 |
| 自己的素材 | 项目 `source/script.txt`、`source/voice-reference.wav`、`source/avatar.mp4`；声音建议 5—15 秒干净授权录音，人物是单人、嘴部清晰、无切镜的授权视频，[详细要求](references/beginner-windows.md#三个文件分别是什么) |
| 字幕与成片工具 | FFmpeg/FFprobe（数字人包提供）、独立 Python 工具环境、对齐模型、Node.js 和 Remotion，[安装与调用](references/beginner-windows.md#6-安装工具环境并串起-plus) |

数字人包接收“**完整配音 + 人物视频**”，不是参考音色或照片。
运行包解压后 `--dh-engine-root` 指向 **`engine` 子目录**。
默认 batch=1、关闭增强；RTX 2070 8GB 已做短片测试，4GB 有显存不足反馈，6GB 未验收。
Plus 生成 `talkcraft-input.json` 后，仍需 Agent 完成字幕动效和 Remotion 渲染，才是最终成片。

**最直接的方式：把仓库链接丢给你的 agent。**
在 Claude Code / Codex 里直接说：

```text
帮我安装这个 skill：https://github.com/haojing8312/easegen-video-talkcraft
```

或用 [skills](https://skills.sh/) CLI / 手动安装：

```bash
npx skills add haojing8312/easegen-video-talkcraft
```

```bash
git clone https://github.com/haojing8312/easegen-video-talkcraft.git
cd easegen-video-talkcraft
ln -s "$(pwd)" ~/.claude/skills/easegen-video-talkcraft   # Claude Code
# 或
ln -s "$(pwd)" ~/.codex/skills/easegen-video-talkcraft    # Codex
```

环境（agent 会按需自行配置）：

- Node.js（Remotion 渲染；依赖安装在 `runtime/`，不要在单片工程内 `npm install`）
- Python 3.10+
  - 本机 CPU 时间戳对齐：`pip install zhconv pypinyin sherpa-onnx soundfile numpy`
    （首次使用下载一次 767MB 的 FireRedASR2-CTC 模型，地址见
    `scripts/timestamps_cpu.py` 头注释；或加 `--backend whisper` 免手动下载）
  - 一键流式配音+时间戳（Fish Audio 免费层）：`pip install requests python-dotenv`
- ffmpeg

然后这样下需求：

```text
用 easegen-video-talkcraft 把这份口播稿 + voiceover.wav 做成视频。
做一条 100 秒的 <话题> 解说，稿子和音频在这里。
用 Plus 流程把这份稿子、音色参考和人物母片生成数字人口播视频。
```

### 🎙️ 可选：Fish Audio 生成配音 + 字级时间戳

默认仍是「成品配音 + 本机 CPU 对齐」。没有录音时，可主动选择 Fish Audio 接入；脚本默认请求 `s2.1-pro-free`，模型的免费额度与可用期限以 Fish Audio 为准。

1. 安装 `ffmpeg` 和 Python 依赖 `pip install requests python-dotenv`。
2. 复制 `.env.example` 为 `.env`，填写 `FISH_AUDIO_API_KEY`。`FISH_AUDIO_REFERENCE_ID` 可填音色库中的音色 ID，留空使用服务默认音色。
3. 准备 `script.json`，例如 `{"sentences": ["这是第一句。", "这是第二句。"]}`；也支持字符串数组或每行一句的 `.txt`。
4. 生成音频与时间戳：
   ```bash
   # 默认逐句模式：每句一次请求，句间插入 0.25 秒真实静音
   python3 scripts/tts_fishaudio.py script.json audio/full.wav audio/timestamps.json --timing-out remotion/src/timing.json
   # 整稿一次请求，保留模型生成的句间节奏
   python3 scripts/tts_fishaudio.py script.json audio/full.wav audio/timestamps.json --timing-out remotion/src/timing.json --mode stream
   ```

两种模式均接收 SSE 音频与对齐快照；`stream` 表示流式接收，**文件在全部生成完成后写出，不提供边生成边播放**。`--pause-sec` 只控制逐句模式额外插入的静音。音频先分别解码成 PCM，再拼接、编码，时间戳按实际采样数累计。`--format mp3|wav|opus` 控制接口返回格式，输出格式由音频文件扩展名决定。

中文沿用接口的字级锚点；英文在词内按字符插值，标点零时长。空音频、缺失/无效对齐、解码失败、规范化后稿子与对齐文本不一致都会报错退出。规范化忽略标点、大小写与字符宽度，不推测 `2` 与 `two` 等读法转换；遇到此类差异请改写为实际朗读文本，或使用已有音频走本机 CPU 对齐。`match=1` / `ok=true` 表示文本映射通过，不代表已人工确认发音或字级精度，仍需试听。

回归验证（无需 API Key，需要 `requests` 与 `ffmpeg`）：
```bash
python3 -m unittest discover -s scripts -p 'test_*fish*.py' -v
```

## 🎞 你提供什么 vs. 它做什么

| 你提供（输入） | skill 负责 |
| --- | --- |
| 口播稿 | 字级时间戳对齐，逐句质检标记 |
| 成品配音——任何 TTS 或真人录音 | SHOTBOOK 分镜：语义拍、层矩阵、排版预算 |
| 或：授权音色参考 + 本地 IndexTTS2 | Plus 管线生成完整配音并保留运行证据 |
| 或：人物母片 + 独立安装的数字人运行时 | 生成并检查口型同步人物视频；不分发第三方权重 |
| 可选的人物素材——普通实拍视频即可（抠像 + 人脸安全区工具已含，绿幕抠得最干净） | Remotion 实现：全局系统（极缓推拉相机/让位）、转场、音效落位 |
| 可选的 B-roll / 截图 | 渲染 + 三重验收（机器闸全过 + 一轮独立审片修完 P0/P1 即交付，可选续审累计 ≤3 轮），响度归一交付 |

## 📦 库里有什么

| 内容 | 说明 |
| --- | --- |
| 108 张动效配方卡 | 意图、能量档、参数、实现要点、已知坑——每张都配自包含 Remotion tsx 源码（`template/cards/`，复制单文件即用）+ 可跑的 HTML demo |
| 画廊 | [在线版](https://vincentwei1021.github.io/video-talkcraft/)或本地 `open gallery/index.html`——108 个预览一页自动播放，按名称/关键词搜索 |
| 动效系统 | CameraRig（极缓推拉）、让位生命周期、六式转场、长镜头世界画布；视差 / 环境层可选（`template/motion-systems/`） |
| 组件 | 素排字幕、花字、砸字、荧光笔、铅笔手绘、数字滚动、视频容器边框八式（`template/components/`） |
| 管线脚本 | 字级时间戳（双 ASR 后端）、人脸安全区检测、静止检测、音效在场检查、QA 抽帧（`scripts/`） |
| 方法论 | 设计语言（Apple 范式默认）、镜头三面工作单、电影感规范、分镜格式、验收口径（`references/`） |
| 内嵌音效 | 逐卡 cue 表 + 真采样内嵌 demo 库（授权见 `demos/_lib/sfx/ATTRIBUTION.md`） |

## 🗂 目录结构

```text
easegen-video-talkcraft/
├── SKILL.md                    # agent 入口：八步管线与硬规则
├── references/
│   ├── design-language.md      # 默认视觉系统（色板/字阶/布局/字幕）
│   ├── shot-design.md          # 三面工作单 + 七型镜头预设
│   ├── cinematography.md       # 七层模型、转场、排版预算、验收关卡
│   ├── shotbook-example.md     # 完整分镜范例
│   ├── cards/                  # 108 张动效配方卡
│   ├── taxonomy.md             # 按类别与来源的卡片索引
│   ├── broll-sources.md        # 免署名素材源（API、授权坑）
│   ├── host-footage.md         # 人物素材：输入规格、抠像、人脸安全区
│   └── demo-spec.md            # 卡片/demo 编写规范
├── demos/                      # 108 个可跑的 HTML 预览（共享库内嵌音效）
├── gallery/                    # 单页本地画廊
├── template/                   # 即取即用的 Remotion 代码
│   ├── cards/                  # 108 卡逐卡自包含 tsx 源码（skill 首选引用）
│   ├── motion-systems/         # 相机/视差/让位/环境/转场/长镜头系统
│   └── components/             # 字幕/花字/砸字/铅笔等组件
└── scripts/                    # 时间戳、人脸检测、QA 工具
```

完整工作流从 [SKILL.md](SKILL.md) 进入。

## ❓ FAQ

**video-talkcraft 是什么？**
一个开源的 AI agent skill（Claude Code / Codex 技能包），用于 AI 视频制作：
把口播稿 + 成品配音自动做成带动效的口播视频。它不是剪辑软件，也不是模板站——
agent 读方法论、选动效配方卡、写 [Remotion](https://www.remotion.dev/) 代码、
跑三重验收，产出可直接发布的解说成片。

**能做哪类视频？**
知识科普、产品评测、新闻解读、观点锐评等口播/解说类横屏视频。
中文口播优先设计，中英混排完全支持。

**需要准备什么？**
口播稿（文本）+ 成品配音（任何 TTS 或真人录音）；人物出镜素材与 B-roll 可选。

**免费吗？**
个人、教育、研究用途免费（PolyForm Noncommercial 1.0.0），
用它做出的视频归你所有；工具本身的商业使用需先授权（见下）。

## 📄 许可

[PolyForm Noncommercial 1.0.0](LICENSE)——个人、教育、研究用途免费。
**将本工具用于任何商业用途需事先获得授权**——发邮件至
[vincentwei1021@gmail.com](mailto:vincentwei1021@gmail.com) 或提 GitHub issue 联系。

本仓库保留上游 Git 历史、Required Notice 与许可条款；Easegen 新增适配代码的第三方运行时边界见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。开放源码可见不等于获得商业使用或模型再分发授权。

**用本 skill 做出的视频归你所有。** 如果它帮到了你，欢迎在视频简介里
@ 一下作者的账号——非强制，但对作者是最好的支持。

## 🔊 音频与素材说明

- 内嵌音效采样的来源与授权：[demos/_lib/sfx/ATTRIBUTION.md](demos/_lib/sfx/ATTRIBUTION.md)。
- B-roll 素材源指南只收免署名源（Pexels、Pixabay、Mixkit Free、Coverr、NASA），
  并记录了被排除源的授权陷阱——见 [references/broll-sources.md](references/broll-sources.md)。
- demo 里的主持人素材（`demos/_lib/dh-host.webm`）是 AI 生成的演示形象占位，
  生产时请替换为你自己的人物素材。

## 🙏 致谢

- **[Remotion](https://www.remotion.dev/)**——驱动全部渲染的 React 视频框架
  （注意其自身[许可](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)）。
- **[FireRedASR2](https://github.com/FireRedTeam/FireRedASR2S)**（经
  **[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)**）与
  **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**——时间戳后端；
  **Qwen3-ASR/ForcedAligner** 是精度基准参照。
- **OpenCV YuNet**——人脸安全区规则背后的检测器。
- **Pexels · Pixabay · NASA · Mixkit**——免署名素材来源。
- **Claude Code**——本库由 AI 编码 agent 构建、迭代与验收，用的正是 skill 自己教的那套评审循环。

## 关注作者

<p>
  <a href="https://www.douyin.com/user/MS4wLjABAAAAK1pkjBxilk2Oi_9h_vFyD-lTAu9CTlvhmOtkosDvvxg"><img alt="在抖音关注作者" src="https://img.shields.io/badge/%E6%8A%96%E9%9F%B3-%E5%85%B3%E6%B3%A8%E6%88%91-000000?style=for-the-badge&logo=tiktok&logoColor=white"></a>
  <a href="https://xhslink.cn/m/At9iP2d5C1V"><img alt="在小红书关注作者" src="https://img.shields.io/badge/%E5%B0%8F%E7%BA%A2%E4%B9%A6-%E5%85%B3%E6%B3%A8%E6%88%91-FF2442?style=for-the-badge&logo=xiaohongshu&logoColor=white"></a>
  <a href="https://x.com/VincentWei93"><img alt="在 X 关注作者" src="https://img.shields.io/badge/X-%E5%85%B3%E6%B3%A8%E6%88%91-000000?style=for-the-badge&logo=x&logoColor=white"></a>
</p>

## 微信讨论群

有建议、反馈或使用问题？扫码加入 video-talkcraft 交流群（2 群）：

<img src="assets/wechat-group.jpg" alt="video-talkcraft 微信交流群二维码" width="300">

二维码更新于 2026-09-17，过期后会不定期更新；也可通过上方社媒直接联系作者。
