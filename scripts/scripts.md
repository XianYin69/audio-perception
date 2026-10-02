# scripts（脚本库）

全部英文文件名、纯 numpy＋标准库实现，不 import 未安装的库。

| 脚本 | 职责 |
|---|---|
| [_cli.py](_cli.py) | 底座：WAV 解码（PCM8/16/24/32、float、extensible）、网关只读调用、tmp 产物、统一失败出口 |
| [deps.py](deps.py) | 依赖守门：缺包只报错＋手动命令，`exit 2`，绝不自动安装 |
| [analyze.py](analyze.py) | 声学编码器：meta/响度/时域/频域/音高/mel-MFCC/chroma/16×24 ASCII 栅格/tokens |
| [perceive.py](perceive.py) | 编码→网关判读：内嵌 14 类锚点提示词、容错解析、固定键输出 |
| [capture.py](capture.py) | 麦克风（可选）：sounddevice→pyaudio→ffmpeg dshow，全不可用 `exit 2` |
| [batch.py](batch.py) | 目录批量：逐文件编码＋判读，汇总 JSON 表＋一行摘要 |

## 约定

- 分帧固定 `HOP=512 / WIN=1024 / 汉宁窗`；FFT 只用 `numpy.fft`；mel 与 DCT 手搓。
- 同输入同输出（确定性可复现）；数值一律 round 到固定位宽再输出。
- 失败即停：`_cli.die()` 打印原因后退出，不重试、不静默降级。
- 产物只落 `env SMS_TMP`（`_cli.tmp_dir()`），不写技能目录。

## 相关

- [SKILL.md](../SKILL.md)
- [schemas](../schemas/schemas.md)
- [resistance](../resistance/resistance.md)
