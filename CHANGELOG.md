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


## 1.0.2（2026-10-02）规格对齐（仅文档，不改任何代码行为）

- 把 1.0.1 已落地但规格未写全的三处实现现状补写进文档，逐条给出判据、参数值、
  适用范围与失效条件；`scripts/` 未改动（py_compile＋两 schema json 解析自检通过）。
- **① 瞬态兜底扩展到任意时长**（SKILL.md／schemas/encoding.json notes／
  knowledge/声学特征字典.md）：`_onset_rate(env, dur, rise, transient)` 当 `transient`
  为真时对**任意 duration** 取 `max(rate, 1.0/dur)`；`transient`＝`_rise_ms`（1ms 块
  RMS，峰值 10%→90%）≤`RISE_MS=10.0` 且 峰值>0 且 `median(1ms 块 RMS)<0.2×峰值`；
  原短段分支 `dur<SHORT_S=0.15 且 rise<10.0` 保留。兜底只抬升不降低。失效条件：
  `dur<=0`、`rise=None`（峰值≤0）、`rise>10ms`、`median>=0.2×峰值`（稳态音）、
  `is_silence`（`_zero_spectral` 置 0）。实测 0.1/1/3/8s 单击输入 onset＝
  10.0/1.0/0.333/0.125。
- **② BPM 时间基改为 20ms 块能量调制＋调制门限**（同上三处；`constants` 新增
  `BLOCK_MS=20.0`、`RISE_BLOCK_MS=1.0`、`ONSET_DB=1.41`、`SHORT_S=0.15`、`RISE_MS=10.0`、
  `BPM_MOD=0.05`、`BPM_AC_MIN=0.3`）：`_bpm(env, BLOCK_MS/1000)` 以 20ms 块 RMS 包络的
  去均值自相关在 30–300 BPM（lag 10..100 块）取峰；块数<8（<160ms）、调制深度
  `std/mean<0.05`、相关峰`<0.3` 一律＝0。取代原规格时间基（帧移 `hop_s`／起音间隔）。
  量化 20ms→120BPM 处 ±1 块＝115.4/125.0；实测调幅音 60/90/120/150/200→
  60.0/90.9/120.0/150.0/200.0，带外 28/32/290/310→300.0（拉回带边，须与
  `onset_rate_hz`、`duration` 交叉复核）；`is_silence` 时置 0。
- **③ feeling 归属写明、不被 normalize 覆盖**（`schemas/perception.json` 字段＋invariants、
  `knowledge/网关输出截断与抢救.md` 新节、`SKILL.md`）：`feeling` 属模型产出，
  `normalize()` 仅 `_as_list(..., r"[、，,;；\s]+")[:6]` 归一截断，不从编码回填；
  1.0.0 的「非 list 即置默认」会把字符串型 feeling 整条丢弃为 `[]`（吞字段），已修。
  `truncated`/`parse_failed` 件里 feeling 可能缺失或仅部分抢救，须随件标注。
- 契约仍为 `ap-enc-1`/`ap-per-1`：只改描述性文本与 `constants`/`notes`/`invariants`，
  键名与 tokens 行格式不变；自检＝全部 `scripts/*.py` 过 `py_compile`、
  两 schema `json.load` 可解析。

## 1.0.1（2026-10-02）实测缺陷修复（ap-fix-spec A/B/C）

- **perceive.py（A·阻断级判读全空）**：SYSTEM 增输出预算与数组类型硬要求；
  `perceive()` 与 `--max-tokens` 默认 1024→2048；新增 `_salvage_json()` 截断抢救
  （剥围栏→括号平衡扫描，忽略字符串内括号与转义→回退最后完整值边界补齐闭合），
  成功附 `truncated:true`；彻底失败写 `parse_failed:true` 并保留 `raw`（截 4000 字），
  不再以空字段冒充正常结果；`_as_list()` 容错拆分被写成一句话的 feeling/uncertainty。
- **_cli.py**：`chat_text()` 返回 `finish_reason`（截断判定用），并对缺 content 容错。
- **唯一重试例外**：`finish_reason=="length"` 且抢救失败时压缩重试一次，
  已在 `resistance/失败即停不重试` 与 `knowledge/网关输出截断与抢救.md` 写明。
- **analyze.py（B·编码质量）**：f0 改为「离散谱峰＋ACF 子倍频候选 → 谐波能量占比
  ≥0.3 校验」，`spectral_flatness>0.4` 强制 f0=0 且 voiced_confidence≤0.2，
  新增 `harmonic_ratio`；起音去噪声底（通量 60 分位基线＋3×MAD，峰须超 1.41×中位包络），
  稳态音 onset<2Hz；短段/冲击兜底（dur<0.15s 且上升<10ms，或瞬态形态 → onset≥1/dur）；
  静音（silence_ratio≥0.95）频域特征全置 0 并新增 `meta.is_silence`；
  BPM 改用包络块时长为时间基并加调制深度/相关峰门限。
- **契约**：只新增键（`is_silence`、`harmonic_ratio`、`truncated`、`parse_failed`），
  既有键名与 tokens 行格式不变；确定性复现（同输入两次全等，11 样本实测）。
- **文档**：SKILL.md 补 `--max-tokens`；新增 `knowledge/网关输出截断与抢救.md`；
  resistance 写明唯一重试例外；schemas 补新增键说明。
- **实测**：chord f0=260.3（vcf 0.699）、wind f0=0、tone440/alarm onset=0、
  knock onset=20.0、silence is_silence=true 且 centroid=0；
  alarm/gunshot/chord/speech_like 网关判读均无 parse_failed，
  `--max-tokens 120` 人为截断可抢救回 type 并标 truncated。全部 .py 过 py_compile，
  未新增第三方依赖（仍只用 numpy＋标准库）。
