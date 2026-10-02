---
name: audio-perception
description: >
  声音感知：把 WAV 用纯 numpy 编成确定性「声音编码」（时域/频域/音高/mel-MFCC/chroma
  ＋16x24 ASCII 谱栅格），交 SMS 纯文本网关判读出类型/听感/对象/情绪/要求（14 类体系＋判别锚点）。
  诚实边界：模型只读数值编码推理，不是真"听"波形；不含 ASR；不安装任何依赖。
license: MIT
metadata:
  category: audio
---

# audio-perception

使用 `audio-perception` skill 来完成用户请求。

## 快速用法

```
python -B scripts/analyze.py  --audio a.wav [--start 0] [--end 5] [--max-sec 10] \
                              [--format text|json|tokens] [--out enc.json]
python -B scripts/perceive.py --audio a.wav [--hint "像警报"] [--max-tokens 2048] [--out res.json] [--raw]
python -B scripts/perceive.py --encoding enc.json          # 复用已存编码，不再算特征
python -B scripts/capture.py  --seconds 5                  # 麦克风（可选后端）
python -B scripts/batch.py    --dir WAV目录 [--no-gateway] [--out all.json]
```

## 流程

WAV 解码（纯标准库）→ numpy 特征编码（确定性）→ 拼提示词 → 网关 `/chat/completions`
→ 容错解析 JSON → 固定键结果（type/feeling/object/emotion/requirement/evidence/uncertainty），契约见 [schemas/](schemas/schemas.md)。

## 能力面（诚实）

- 模型**不"听"波形**，只读数值编码＋ASCII 谱栅格推理；细粒度千类声事件不可靠，
  须降 confidence 并写进 `uncertainty`。
- 只解码 WAV（PCM8/16/24/32、IEEE-float）；非 WAV 需自行转码（模板见
  [WAV解码注意](knowledge/WAV解码注意.md)），本技能不代装 ffmpeg。
- 语音内容（说了什么）需 ASR，本技能不含：只判"是语音＋情绪"。
- 编码确定性可复现；两次判读不一致时以 `evidence` 引用的特征值为准；网关输出被截断时先抢救再标 `truncated`，救不回标 `parse_failed`，见 [网关输出截断与抢救](knowledge/网关输出截断与抢救.md)。

## 红线

不安装依赖；不写技能目录以外的缓存（产物落工作区 tmp）；api_key 绝不打印；
失败即停不重试（唯一例外：截断抢救失败后压缩重试一次）；不夸大识别率。详见 [resistance/](resistance/resistance.md)。

## 目录

[scripts/](scripts/scripts.md) · [knowledge/](knowledge/knowledge.md) ·
[resistance/](resistance/resistance.md) · [schemas/](schemas/schemas.md) ·
[dependence/](dependence/dependence.md) · [planned_tasks/](planned_tasks/README.md) · [asset/](asset/asset.md) · [agent/](agent/agent_prompt.md)
