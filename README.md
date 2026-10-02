# audio-perception

声音感知 Skill：把「声音的编码」作为输入交给大模型，模型输出声音的
类型 / 感觉 / 对象 / 情绪 / 要求，覆盖 14 类常见声音。

## 它是怎么"听"的

本技能**不**把音频喂给模型（网关只有纯文本通道）。它先用纯 numpy 把 WAV 编成
确定性特征文本（含 16×24 ASCII 谱栅格），再让模型对数字与字符矩阵做推理。
因此它是"读声学报告"，不是"听声音"——详见 [能力边界](resistance/能力边界/能力边界.md)。

## 入口

- [SKILL.md](SKILL.md)：YAML frontmatter 入口，可直接注入 agent。
- [agent/](agent/agent_prompt.md)：四格式提示词（CLAUDE.md / .cursorrules / instructions.md）。
- [scripts/](scripts/scripts.md)：analyze / perceive / capture / batch / _cli / deps。
- [knowledge/](knowledge/knowledge.md)：特征字典、14 类体系与锚点、网关调用、WAV 解码注意。
- [schemas/](schemas/schemas.md)：`ap-enc-1` 编码契约、`ap-per-1` 判读契约。
- [resistance/](resistance/resistance.md)：六条约束（不装依赖、不越界写缓存、不复述 api_key、
  失败即停、不夸大识别率、能力边界）。
- [dependence/](dependence/dependence.md)：[deps.json](dependence/deps.json)（每条附 source_url）。
- [planned_tasks/](planned_tasks/README.md)：计划任务声明（到期由 SMS 调度器执行）。
- [asset/](asset/asset.md)：技能包资产。

## 最小示例

```
python -B scripts/analyze.py --audio a.wav --format tokens
python -B scripts/perceive.py --audio a.wav --out result.json
```

## 许可

[MIT](LICENSE)。
