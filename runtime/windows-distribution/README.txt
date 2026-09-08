Easegen 数字人 Windows 原生运行包

这是数字人模块，不是完整的口播稿到成片套装。配音 IndexTTS2、字幕和 Remotion 请按 Skill 新手指南安装。
Skill：https://github.com/haojing8312/easegen-video-talkcraft
指南：https://github.com/haojing8312/easegen-video-talkcraft/blob/main/references/beginner-windows.md

1. 解压整个文件夹，不要在压缩包内直接运行。建议 D:\Easegen\avatar-runtime。
2. 需要 Windows x64 和兼容的 NVIDIA 驱动。RTX 2070 8GB 已做短片测试；4GB/6GB 未验证。
   AMD、Intel 核显和纯 CPU 目前不能运行此数字人后端。不使用 WSL/Docker/Redis。
3. 双击 check.cmd。它检查文件及 CUDA Provider 可用性，不代表已经完成真实推理。
4. 放入自己的素材（目录不存在时新建）：
   input\audio.wav：完整口播配音，非仅用于克隆的参考声音；建议 PCM WAV。
   input\avatar.mp4：单人、正脸或轻微侧脸、嘴部清晰、稳定光线、无切镜的真人视频。
   先试 3—5 秒音频和短人物视频。人物视频短于音频时会循环，重复动作可能被看出。
5. 双击 render.cmd，结果在 output\host.mp4。已有结果不会被静默覆盖；请换名称或移走旧结果。
   没有输出且命令报错，不能把旧视频视为本次成功。先查看控制台及 output\.heygem-jobs 下诊断文件。
6. 接入 Skill 时，--dh-engine-root 必须指向本包的 engine 子目录：
   D:\Easegen\avatar-runtime\engine
   不要指向 zip，也不要只指向其上一层。

高级调用（PowerShell，在运行包目录执行）：
  .\engine\py39\python.exe -B -s .\avatar_runtime.py render --audio D:\my-video\audio.wav --avatar D:\my-video\avatar.mp4 --output D:\my-video\host.mp4

默认 batch=1、人脸增强关闭。Python 目录 py39 实际为 3.10.16；原生扩展绑定此版本，请勿自行升级。
本包未包含私人声音、人物照片/视频或测试成品；请使用本人或明确授权素材，勿冒充他人。
不得将自己用过的 input/output/.heygem-jobs 文件夹直接重新上传分享。
模型与依赖首次复制到其他磁盘时会占额外空间；每次任务还会保留诊断和中间文件。

分发权限由发布者确认。第三方组件的条款仍适用，licenses 及依赖目录中的许可证应保留。
付费安装服务不等于商业使用授权。此包不包含 NVIDIA 显卡驱动，也不会改动系统 DLL 目录。
问题联系 Easegen 维护者：仓库 README 中“Easegen 作者微信”二维码，备注 easegen 数字人运行包；
或 https://github.com/haojing8312/easegen-video-talkcraft/issues 。不要在公开 Issue 上传私人素材或完整私人日志。
