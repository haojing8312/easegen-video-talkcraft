# 数字人运行包：维护者打包与发布

此流程只适用于已获得分发许可的兼容 Windows ONNX 引擎。GitHub 只收脚本和文档；运行环境、模型独立交付，不能提交到 Git。
本次分发权限由项目维护者确认；保留代码、模型、运行库的独立许可，不将安装服务费用描述成商业授权。

## 可重复构建

在 Skill 根目录执行，输出必须是源引擎和 Skill 仓库之外的**全新目录**：

```powershell
python scripts/package_avatar_runtime.py `
  --source F:\worksoft\heygem-win-50-onnx `
  --output F:\EasegenReleases\easegen-avatar-runtime-win-x64-1.0.0 `
  --version 1.0.0 --redistribution-confirmed
```

脚本采用必要代码/模型目录清单，复制兼容 Python 环境；真实复制，不改原引擎、不使用可被清理操作误改的硬链接。
包括直接推理所需的 DINet、WeNet、人脸模块、可选增强/音频处理模型、FFmpeg 和 Skill 适配器。
不包含原 Gradio UI 或生产 Redis/对象存储服务，也不包含 IndexTTS2、字幕及 Remotion 环境。

默认排除：全部常见声音/视频/人物图片文件、输出、缓存、日志、测试目录、历史记录、开发性能分析器、嵌套压缩包、`.env`、安装路径元数据。
重新生成配置：回环地址、注册关闭、batch=1、人脸增强关闭；模型文件不做量化或格式转换。
`manifest.json` 记录每个发布文件的相对路径、字节数和 SHA256；保留依赖自带许可证和项目第三方声明。
这是文件清单式隐私清理，不是对闭源二进制及模型内容的完整安全审计。

## 先验收，再压缩

1. 用包内 `engine/py39/python.exe -B -s avatar_runtime.py check` 检查路径与 Provider。
2. 用包内 Python/适配器做真实短片，输入、输出均放**分发目录外**。测试私人素材允许用于本地验证，但不能进入上传目录。
3. 检查返回 CUDA Provider、音视频流、时长、完整解码及实际口型；不能只看 `--check` 或输出文件存在。
4. 检查清单中没有素材/密钥/运行记录，没有原电脑私有配置；不把私人诊断附进包。
5. 压缩前严格验证构建后文件未增删改：

```powershell
python scripts/package_avatar_runtime.py `
  --source F:\worksoft\heygem-win-50-onnx `
  --output F:\EasegenReleases\easegen-avatar-runtime-win-x64-1.0.0 `
  --version 1.0.0 --redistribution-confirmed --archive-only
```

生成 ZIP64 和旁边 `.zip.sha256`，并完整测试 ZIP CRC。ZIP 使用低压缩级别以控制构建时间，不代表体积最小。
上传前最好再次解压到新路径，在另一台无开发环境的电脑验收；本机迁移成功不代表所有电脑已验证。
切勿压缩已被用户使用过的运行包目录，否则其中 `input/`、`output/` 和 `.heygem-jobs/` 会包含私人素材。

## 百度网盘发布清单

- 上传 `.zip` 与 `.zip.sha256`；不要上传同级私有测试文件或整个父文件夹。
- 记录链接、提取码、版本、文件大小、校验值、发布日期、对应 Skill 提交。
- 将真实入口补到 README 和新手指南；没有真实链接时保留“联系 Easegen 维护者获取”，不要造链接。
- 下载用户可运行 `Get-FileHash <zip路径> -Algorithm SHA256` 对照校验。
- 标明：NVIDIA RTX 2070 8GB 短片已测，4GB/6GB 未验证；运行包只覆盖数字人阶段。
- 未随包提供私人声音或人物素材；输入要求、放置目录与接入命令见包内 `README.txt` 和[新手指南](beginner-windows.md)。

上传到百度网盘需要维护者账户和实际上传操作，本地打包完成不等于已对外上传。

## 1.0.0 本机迁移验收（2026-09-07）

发布文件：`easegen-avatar-runtime-win-x64-1.0.0.zip`。
压缩大小 **8,058,183,554 字节（约 8.06 GB / 7.50 GiB）**，解压约 **12.01 GiB**，不含任务中间文件占用。
ZIP CRC 全量检查通过，包内 34,550 个文件（含清单）与清单核对一致；随包附 `input/`、`output/` 空目录。

SHA256：

```text
6c00f933b5ae885a8d0ffcc705ed6f434df1a6fa36e682aa4ec62414f7da378e
```

- 使用清理后运行包的新绝对路径、包内 Python 和适配器；测试进程 PATH 仅保留 Windows 系统目录，再由适配器添加包内依赖路径。
- Hugging Face / Torch 缓存指向新的私有测试目录，并设置 Hugging Face/Transformers 离线标志；这不是操作系统级断网或另一台干净电脑的证明。
- RTX 2070 8GB，batch=1、FP32、增强关闭，480×832 / 30fps，约 2.05 秒输入：真实 DINet CUDA Session、H.264 + AAC、时长一致、完整解码通过；输出与原有基准逐字节一致。
- 人脸抽检 3 帧全部检出。整卡显存采样峰值 3143 MiB，包含其他程序，不是进程独占显存或 4GB 显卡可运行的证明。
- 修复 Numba 编译缓存写入依赖目录的问题，改存每个任务 `tmp/numba-cache`；复测后发布目录没有新增缓存，逐文件清单仍匹配。
- 测试输入、输出、日志和人脸安全区文件均在分发目录外，不随包提供。本次验证不覆盖全新电脑安装、长片、高分辨率或完整 IndexTTS2/Remotion 流程。
