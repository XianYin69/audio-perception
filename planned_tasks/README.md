# planned_tasks（计划任务声明）

一任务一文件：`pt-audio-perception-<slug>.json`。字段名与 SMS 读取端
（`skill/scripts/planned_tasks.py` 的 `FIELDS`）一致，不得改动。

## 语义

- 到期由 **SMS 调度器**读取执行并挂 session 关联链；**本技能自身不得执行计划任务**，只声明。
- 删除文件即注销该任务。
- `status` 仅 pending / running / done / paused / failed；时间一律本地 ISO。

## 字段

| 字段 | 含义 |
|---|---|
| id | 与文件名一致：`pt-audio-perception-<slug>` |
| title | 一句话说明 |
| skill | 归属技能 id（`audio-perception`） |
| input | 到期要执行的诉求文本 |
| schedule | `{mode: at\|cron\|interval, at, cron, every_min}` |
| session | `{kind: "cron", key: "<skill>:pt-..."}` |
| status | 见上 |
| created / next_run / last_run | 本地 ISO（last_run 可为 null） |
| runs / notify / depends | 次数、通知渠道、依赖任务 id |

## 当前内容

- [template.json](template.json)：空模板（复制后改名填值）。
- [pt-audio-perception-recalibrate.json](pt-audio-perception-recalibrate.json)：
  锚点阈值复标（合成样本阈值需用真实录音复核）。

## 相关

- [SKILL.md](../SKILL.md)
- [resistance](../resistance/resistance.md)
