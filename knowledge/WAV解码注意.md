# WAV 解码注意

`_cli.read_wav()` 纯标准库实现（`struct`/`array`/numpy），不依赖 soundfile、librosa、
pydub；`audioop` 在 Python 3.13 已移除，本技能不引用。

## 支持范围

- RIFF/WAVE 容器，`fmt ` + `data` 块。
- 编码：PCM 8/16/24/32 位整数、IEEE float 32/64（tag=3）、
  WAVE_FORMAT_EXTENSIBLE（tag=0xFFFE，读子格式 GUID 前 2 字节）。
- 多声道：按声道求均值降为单声道后分析。
- 8-bit 视为无符号（减 128 归一）；24-bit 手工符号扩展。

## 不支持（直接报错，不猜测）

- 压缩 WAV：MS_ADPCM(0x0002)、IMA_ADPCM(0x0011)、AMR、μ-law/A-law(0x0007)。
- 非 WAV：mp3、ogg、flac、m4a、aac、webm、opus。
- 缺 `fmt`/`data`、采样率或声道为 0、data 长度非帧对齐整数倍（尾部按可用截断）。

## 转码模板（本技能不代装 ffmpeg）

```
ffmpeg -i IN.mp3 -ac 1 -ar 44100 -acodec pcm_s16le OUT.wav
ffmpeg -i IN.mp3 -t 10 -ss 3 -acodec pcm_s16le OUT.wav   # 先裁 3s 起 10s
```

未装 ffmpeg 的提示（不自动安装）：`winget install Gyan.FFmpeg`。

## 采样率相关坑

- 特征频率上限＝sr/2：8k 电话录音看不到 4kHz 以上，玻璃摩擦类质心特征会失真，
  应在 uncertainty 注明"采样率不足"。
- HOP=512 / WIN=1024 固定：sr 越低时间分辨率越粗（16k→32ms/帧，48k→10.7ms/帧）。
- f0 搜索限 50-4000Hz；低于 50Hz 的次声与高于奈奎斯特的成分一律测不到。
- 削波阈值 0.995 基于归一化幅值，float 录音超范围（|x|>1）同样计入 clipping_ratio。
