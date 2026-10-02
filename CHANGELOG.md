# CHANGELOG

## 1.0.0（2026-10-02）audio-perception 首版

- 由 Skill_Generator 创建路径按 `audio-perception-spec.md` 0~7 节落地。
- scripts：`_cli.py`（纯标准库 WAV 解码 PCM8/16/24/32＋IEEE-float＋extensible、
  网关只读调用、tmp 产物）、`deps.py`（缺包只报错不安装）、`analyze.py`
  （纯 numpy 编码器：HOP=512/WIN=1024 汉宁窗、mel 40 带与 DCT 手搓、13 维 MFCC、
  chroma 12、16×24 ASCII 谱栅格、tokens 行）、`perceive.py`（编码→网关判读＋容错解析）、
  `capture.py`（可选录音三级降级）、`batch.py`（目录批量）。
- knowledge：声学特征字典、声音类别体系（14 类＋锚点）、网关文本调用、WAV 解码注意。
- resistance：不安装依赖、不写技能目录外缓存、不复述api_key、失败即停不重试、
  不夸大识别率、能力边界。
- schemas：`encoding.json`（ap-enc-1）、`perception.json`（ap-per-1）。
- planned_tasks：README＋template＋`pt-audio-perception-recalibrate`（阈值复标）。
- 实测：Python 3.14.5 / numpy 2.5.2；编码确定性已验证（同输入同输出）。
- 待办（主流程 t4/t5）：网关实判读端到端、技能注册。
