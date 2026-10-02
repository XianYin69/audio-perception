# dependence（依赖清单）

清单文件：[deps.json](deps.json)——每条依赖必附 `source_url` 原始链接，
校验：`python -B <Skill_Generator>/scripts/lint-deps.py --root <本技能目录>`。

## 分级

| 依赖 | 级别 | 缺失后果 |
|---|---|---|
| numpy | hard | 无法编码（`deps.require` exit 2） |
| 标准库 wave/struct/array/json/math | hard | 随 CPython，无需安装 |
| SMS llm_gateway（local://skill_manage_system） | hard | 无法判读，只能交付编码 |
| screen-vision gw 范式（local://screen-vision） | soft | 仅调用范式参照 |
| sounddevice / pyaudio / ffmpeg | optional | 录音与非 WAV 转码不可用 |

## 原则

- 不自动安装：缺包只打印手动命令并退出（[不安装依赖](../resistance/不安装依赖/不安装依赖.md)）。
- 已实测环境：Python 3.14.5、numpy 2.5.2；librosa/soundfile/scipy/pydub/torchaudio 未装，
  `audioop` 在 3.13 已移除——本技能一律不 import。
- 安装时 SMS 同检同净化：`source_url` 指向 GitHub/官方仓库/发布页原始链接。

## 相关

- [SKILL.md](../SKILL.md)
- [scripts/deps.py](../scripts/deps.py)
