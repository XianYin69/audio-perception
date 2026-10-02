"""_cli - audio-perception 共用底座：WAV 解码、网关只读、产物落 tmp。

红线：不安装依赖；不打印 api_key；缓存/产物只落工作区 tmp，绝不写技能目录。
"""
import array
import json
import os
import struct
import sys
import urllib.error
import urllib.request

import numpy as np

TAG = "[audio-perception]"
FLOAT_FMT = 3
EXTENSIBLE = 0xFFFE


def die(msg, code=1):
    """统一失败出口：打印原因并退出，不重试。"""
    print(f"{TAG} 错误：{msg}", file=sys.stderr)
    sys.exit(code)


def sms_home():
    """SMS 根目录（config/config.json 的上游）。"""
    return os.environ.get("SMS_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SMS")


def gateway_cfg():
    """直读 SMS config.json 的 llm_gateway；缺失即退出，不复制不重建。"""
    path = os.path.join(sms_home(), "config", "config.json")
    if not os.path.exists(path):
        die(f"找不到 SMS 配置 {path}")
    with open(path, encoding="utf-8") as fh:
        g = (json.load(fh) or {}).get("llm_gateway") or {}
    if not g.get("base_url"):
        die("config.json 的 llm_gateway.base_url 为空")
    return g


def tmp_dir():
    """产物目录＝工作区 tmp（env SMS_TMP），永不写技能目录。"""
    d = os.environ.get("SMS_TMP") or os.path.join(
        os.environ.get("TEMP", os.path.expanduser("~")), "audio_perception")
    os.makedirs(d, exist_ok=True)
    return d


def emit(text, out=None):
    """写 stdout 或落文件（UTF-8, LF）。"""
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print(f"{TAG} 已写出 {out}")
        return
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


# ---------- WAV 解码（纯标准库：PCM8/16/24/32、IEEE-float、extensible） ----------


def _chunks(data):
    """遍历 RIFF 子块，产出 (tag, body)。"""
    pos, n = 12, len(data)
    while pos + 8 <= n:
        tag = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        yield tag, data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)


def _parse_fmt(body):
    """fmt 块 -> (tag, channels, rate, bits)；extensible 取子格式。"""
    tag, ch, rate, _br, _al, bits = struct.unpack("<HHIIHH", body[:16])
    if tag == EXTENSIBLE and len(body) >= 26:
        tag = struct.unpack("<H", body[24:26])[0]
    return tag, ch, rate, bits


def _int24(raw):
    """24-bit 有符号整数手工展开。"""
    buf = bytearray(raw)
    buf += b"\x00" * ((-len(buf)) % 3)
    vals = array.array("i")
    for i in range(0, len(buf) - 2, 3):
        w = buf[i] | (buf[i + 1] << 8) | (buf[i + 2] << 16)
        vals.append(w - (1 << 24) if w & (1 << 23) else w)
    return np.asarray(vals, dtype=np.float64) / 8388608.0


def _to_float(raw, tag, bits):
    """样本字节 -> float64 归一化 [-1,1]。"""
    if tag == FLOAT_FMT:
        dt = {32: "<f4", 64: "<f8"}.get(bits)
        if not dt:
            die(f"不支持的浮点位深 {bits}")
        return np.frombuffer(raw, dtype=dt).astype(np.float64)
    if bits == 8:
        a = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
        return (a - 128.0) / 128.0
    if bits == 16:
        return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if bits == 24:
        return _int24(raw)
    if bits == 32:
        return np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    die(f"不支持的位深 {bits}（仅 PCM 8/16/24/32 与 float 32/64）")


def read_wav(path):
    """解码 WAV -> (mono float64, sr, channels, bits, frames)。"""
    try:
        data = open(path, "rb").read()
    except OSError as exc:
        die(f"无法读取 {path}: {exc}")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        die(f"{path} 非 WAV；先转码：ffmpeg -i IN -acodec pcm_s16le -ar 44100 OUT.wav")
    fmt = raw = None
    for tag, body in _chunks(data):
        if tag == b"fmt ":
            fmt = body
        elif tag == b"data" and raw is None:
            raw = body
    if fmt is None or raw is None:
        die("缺少 fmt 或 data 块，文件不完整")
    tag, ch, sr, bits = _parse_fmt(fmt)
    if not sr or not ch:
        die("fmt 块采样率/声道为 0，文件损坏")
    x = _to_float(raw, tag, bits)
    usable = (len(x) // ch) * ch
    x = x[:usable]
    mono = x.reshape(-1, ch).mean(axis=1) if ch > 1 else x
    return mono, sr, ch, bits, len(mono)


# ---------- 网关文本调用（照抄 screen-vision 范式：直读配置、api_key 绝不打印） ----------


def chat_text(messages, max_tokens=None):
    """POST /chat/completions（纯文本 messages，无 audio 通道）-> dict。"""
    g = gateway_cfg()
    url = g["base_url"].rstrip("/") + "/chat/completions"
    body = {"model": g.get("model") or "auto",
            "max_tokens": max_tokens or g.get("max_tokens") or 1024,
            "temperature": g.get("temperature", 1),
            "top_p": g.get("top_p", 0.1),
            "messages": messages}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + str(g.get("api_key", ""))})
    try:
        with urllib.request.urlopen(req, timeout=g.get("timeout", 120)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        die(f"网关返回 {exc.code}: "
            f"{exc.read()[:300].decode('utf-8', 'replace')}")
    except urllib.error.URLError as exc:
        die(f"网关不可达：{exc.reason}")
    except json.JSONDecodeError as exc:
        die(f"网关响应非 JSON：{exc}")
    choices = payload.get("choices") or []
    if not choices:
        die("网关响应无 choices")
    return {"reply": choices[0]["message"]["content"],
            "usage": payload.get("usage") or {},
            "model": payload.get("model", body["model"])}
