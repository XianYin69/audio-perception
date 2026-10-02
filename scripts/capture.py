"""capture - 麦克风录音（可选能力·不硬依赖）。

优先级：sounddevice -> pyaudio -> ffmpeg dshow。
三者全不可用：打印精确安装命令并 exit 2，绝不自动安装（红线）。
录音产物一律落工作区 tmp（env SMS_TMP），不写技能目录。
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import time
import wave

import _cli as cli
import deps

HINT = (
    "本技能不自动安装任何依赖。请自行确认后手动执行其一：\n"
    "  python -m pip install sounddevice\n"
    "  python -m pip install pyaudio\n"
    "  或安装 ffmpeg 并加入 PATH：winget install Gyan.FFmpeg"
)


def _via_sounddevice(path, seconds, sr):
    """sounddevice 录单声道 16bit。"""
    import numpy as np
    import sounddevice as sd
    rec = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="int16")
    sd.wait()
    _write_pcm(path, np.asarray(rec).reshape(-1), sr)
    return True


def _via_pyaudio(path, seconds, sr):
    """pyaudio 流式采集。"""
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = pa.open(rate=sr, channels=1, format=pyaudio.paInt16, input=True,
                     frames_per_buffer=1024)
    frames = []
    for _ in range(int(sr / 1024 * seconds)):
        frames.append(stream.read(1024, exception_on_overflow=False))
    stream.stop_stream()
    stream.close()
    pa.terminate()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(frames))
    return True


def _write_pcm(path, ints, sr):
    """int16 序列 -> WAV。"""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(ints)}h", *[int(v) for v in ints]))


def _via_ffmpeg(path, seconds, sr):
    """ffmpeg dshow 直录（Windows）。"""
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "dshow", "-i", "audio=Microphone Array",
           "-t", str(seconds), "-ac", "1", "-ar", str(sr),
           "-c:a", "pcm_s16le", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{cli.TAG} ffmpeg 录音失败：{r.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def record(seconds, sr=16000, path=None):
    """按优先级尝试录音，返回 WAV 路径；全不可用 exit 2。"""
    path = path or os.path.join(cli.tmp_dir(),
                                f"capture_{time.strftime('%Y%m%d_%H%M%S')}.wav")
    if not deps.have("sounddevice"):
        if not deps.have("pyaudio"):
            if not _via_ffmpeg(path, seconds, sr):
                print(f"{cli.TAG} 无可用录音后端（sounddevice/pyaudio/ffmpeg dshow）。\n{HINT}",
                      file=sys.stderr)
                sys.exit(2)
            return path
        _via_pyaudio(path, seconds, sr)
        return path
    _via_sounddevice(path, seconds, sr)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="麦克风录音 -> 声音编码 -> 判读")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--rate", type=int, default=16000)
    ap.add_argument("--out", default=None, help="编码/结果输出文件（默认 stdout）")
    ap.add_argument("--hint", default=None)
    a = ap.parse_args(argv)
    if a.seconds <= 0 or a.seconds > 60:
        cli.die("--seconds 需在 1-60 之间")
    path = record(a.seconds, a.rate)
    print(f"{cli.TAG} 录音已存 {path}")
    import perceive
    return perceive.main(["--audio", path, "--max-sec", str(a.seconds),
                         "--out", a.out] if a.out else
                        ["--audio", path, "--max-sec", str(a.seconds)])


if __name__ == "__main__":
    raise SystemExit(main())
