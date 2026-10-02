# CONTRIBUTORS

- **Skill_Generator**（创建路径执行者）：按规格落地目录、脚本、知识库、约束与契约。
- **SMS 主流程**（调度方）：提出规格 `audio-perception-spec.md`，负责 t4 端到端实测与 t5 注册。
- **screen-vision**（范式来源）：`scripts/gw.py` 的网关只读调用范式（直读配置、api_key 不打印）。
- **环境事实来源**：本机实测 Python 3.14.5＋numpy 2.5.2，librosa/soundfile/scipy/pydub 未安装，
  `audioop` 自 3.13 移除，ffmpeg 不在 PATH——设计据此限定为纯 numpy＋标准库。
