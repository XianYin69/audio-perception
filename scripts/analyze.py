"""analyze - 纯 numpy 声学编码器：把声音变成确定性「声音编码」文本。

只用 numpy.fft；mel 滤波器组与 DCT 手搓；同输入必同输出（可复现）。
红线：不安装依赖、缺库只报错；产物只落工作区 tmp。
"""
import argparse
import json
import math
import os

import numpy as np

import _cli as cli
import deps

deps.require(["numpy"])

HOP = 512
WIN = 1024
N_MEL = 40
N_MFCC = 13
GRID_T = 16
GRID_F = 24
BANDS = 7
RAMP = " .:-=+*#%@"

HARM_MIN = 0.3
FLAT_TONAL = 0.4
PROM_MIN = 10.0
ONSET_DB = 1.41
RISE_MS = 10.0
SHORT_S = 0.15
SIL_RATIO = 0.95
BPM_MOD = 0.05
BPM_AC_MIN = 0.3
BLOCK_MS = 20.0



def dbfs(x):
    """线性幅值 -> dBFS（下限 -120）。"""
    return 20.0 * math.log10(max(float(x), 1e-6))


def stft(mono, sr):
    """汉宁窗分帧 -> (mag 帧×bin, freqs)。"""
    if len(mono) < WIN:
        mono = np.pad(mono, (0, WIN - len(mono)))
    n_frames = 1 + (len(mono) - WIN) // HOP
    idx = np.arange(WIN)
    win = 0.5 - 0.5 * np.cos(2.0 * math.pi * idx / WIN)
    starts = np.arange(n_frames) * HOP
    frames = mono[starts[:, None] + idx[None, :]] * win
    mag = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(WIN, 1.0 / sr)
    return mag, freqs


def meta_feats(mono, sr, bits, channels, clip_thr=0.995):
    """meta：时长/采样率/声道/位深/削波率/静音比/是否静音。"""
    dur = len(mono) / float(sr)
    clipped = float(np.mean(np.abs(mono) >= clip_thr)) if len(mono) else 0.0
    rms_blk = _block_rms(mono, sr)
    sil = float(np.mean(rms_blk < 0.01)) if rms_blk.size else 1.0
    return {"duration": round(dur, 4), "sample_rate": int(sr), "channels": int(channels),
            "bit_depth": int(bits), "clipping_ratio": round(clipped, 5),
            "silence_ratio": round(sil, 4), "is_silence": bool(sil >= SIL_RATIO)}

def _block_rms(mono, sr, block_ms=BLOCK_MS):
    """按块 RMS 包络（默认 20ms）。"""
    n = max(1, int(sr * block_ms / 1000.0))
    usable = (len(mono) // n) * n
    if usable == 0:
        return np.zeros(1)
    return np.sqrt((mono[:usable].reshape(-1, n) ** 2).mean(axis=1))

def loudness_feats(mono, sr):
    """响度：RMS/峰值 dBFS、动态范围、包络方差。"""
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    rms = float(np.sqrt(np.mean(mono ** 2))) if len(mono) else 0.0
    env = _block_rms(mono, sr)
    lo = float(np.percentile(env, 10)) if env.size else 0.0
    hi = float(np.percentile(env, 95)) if env.size else 0.0
    return {"rms_dbfs": round(dbfs(rms), 2), "peak_dbfs": round(dbfs(peak), 2),
            "dynamic_range_db": round(dbfs(hi) - dbfs(lo), 2),
            "envelope_var": round(float(np.var(env)), 6)}


def time_feats(mono, sr, env):
    """时域：过零率均值/标准差、起音率、包络自相关估 BPM。"""
    zc = np.abs(np.diff(np.sign(mono))) > 0
    hop_s = HOP / float(sr)
    frames = _frame(zc.astype(np.float64))
    zcr = frames.mean(axis=1) if frames.size else np.zeros(1)
    dur = len(mono) / float(sr)
    rise = _rise_ms(mono, sr)
    onset = _onset_rate(env, dur, rise, _is_transient(mono, sr, rise))
    return {"zcr_mean": round(float(zcr.mean()), 5), "zcr_std": round(float(zcr.std()), 5),
            "onset_rate_hz": round(onset, 3),
            "bpm": round(_bpm(env, BLOCK_MS / 1000.0), 1), "hop_s": round(hop_s, 5)}


def _rise_ms(mono, sr, block_ms=1.0):
    """包络上升时间（峰值 10%→90%，毫秒；1ms 块分辨率）。"""
    e = _block_rms(mono, sr, block_ms)
    pk = float(e.max()) if e.size else 0.0
    if pk <= 0.0:
        return None
    i10 = int(np.argmax(e >= 0.1 * pk))
    i90 = int(np.argmax(e >= 0.9 * pk))
    return round(float(max(0, i90 - i10) * block_ms), 2)


def _is_transient(mono, sr, rise):
    """冲击形态：上升 <10ms 且峰值远高于中位包络（稳态音不算）。"""
    if rise is None or rise > RISE_MS:
        return False
    e = _block_rms(mono, sr, 1.0)
    pk = float(e.max()) if e.size else 0.0
    return bool(pk > 0.0 and float(np.median(e)) < 0.2 * pk)

def _frame(vec):
    """按 hop 分帧（不足一帧则丢弃尾巴）。"""
    n = (len(vec) // HOP) * HOP
    if n == 0:
        return np.zeros((1, len(vec)))
    return vec[:n].reshape(-1, HOP)


def _onset_rate(env, dur, rise=None, transient=False):
    """谱通量近似：减噪声底（60 分位基线＋3×MAD）后计显著峰；冲击兜底。"""
    rate = 0.0
    if env.size >= 3 and dur > 0:
        flux = np.maximum(np.diff(env), 0.0)
        base = float(np.percentile(flux, 60))
        mad = float(np.median(np.abs(flux - base)))
        thr = base + 3.0 * mad
        med = float(np.median(env))
        if thr > 0.0 and med > 0.0:
            seg = flux[1:-1]
            loc = (seg >= flux[:-2]) & (seg > flux[2:])
            sig = (seg > thr) & (env[2:-1] > ONSET_DB * med) & loc
            rate = float(np.sum(sig)) / dur
    if dur > 0 and (transient or (dur < SHORT_S and rise is not None
                                  and rise < RISE_MS)):
        rate = max(rate, 1.0 / dur)
    return rate

def _bpm(env, blk_s):
    """包络自相关估节拍（30-300 BPM 带内取峰）；无调制或相关弱则 0。"""
    if env.size < 8 or blk_s <= 0:
        return 0.0
    mean = float(env.mean())
    if mean <= 0 or float(np.std(env)) / mean < BPM_MOD:
        return 0.0
    e = env - mean
    ac = np.correlate(e, e, mode="full")[env.size - 1:]
    ac = ac / (ac[0] if ac[0] != 0 else 1.0)
    lo, hi = int(60.0 / 300.0 / blk_s), int(60.0 / 30.0 / blk_s)
    lo, hi = max(lo, 1), min(hi, ac.size - 1)
    if hi <= lo or float(ac[lo:hi + 1].max()) < BPM_AC_MIN:
        return 0.0
    best = lo + int(np.argmax(ac[lo:hi + 1]))
    return 60.0 / (best * blk_s) if best else 0.0

def _spec_moments(mag, freqs):
    """谱质心/带宽/85% 滚降/平坦度/偏度/峰度（帧均值）。"""
    p = mag + 1e-12
    w = p / p.sum(axis=1, keepdims=True)
    cen = (w * freqs).sum(axis=1)
    bw = np.sqrt((w * (freqs - cen[:, None]) ** 2).sum(axis=1))
    cum = np.cumsum(w, axis=1)
    roll = freqs[np.argmax(cum >= 0.85, axis=1)]
    geo = np.exp(np.log(p).mean(axis=1))
    flat = geo / (p.mean(axis=1) + 1e-12)
    d = freqs - cen[:, None]
    var = (w * d ** 2).sum(axis=1) + 1e-18
    skew = (w * d ** 3).sum(axis=1) / var ** 1.5
    kurt = (w * d ** 4).sum(axis=1) / var ** 2 - 3.0
    return {"spectral_centroid_hz": round(float(cen.mean()), 1),
            "spectral_bandwidth_hz": round(float(bw.mean()), 1),
            "rolloff85_hz": round(float(roll.mean()), 1),
            "spectral_flatness": round(float(flat.mean()), 4),
            "spectral_skewness": round(float(skew.mean()), 3),
            "spectral_kurtosis": round(float(kurt.mean()), 3)}


def _band_contrast(mag, freqs, n=BANDS):
    """n 个对数等分频带的帧内 log 能量对比。"""
    edges = np.geomspace(max(freqs[1], 30.0), freqs[-1], n + 1)
    out = []
    logmag = np.log(mag + 1e-9)
    for i in range(n):
        sel = (freqs >= edges[i]) & (freqs < edges[i + 1])
        out.append(round(float(logmag[:, sel].mean(axis=1).mean()), 3) if sel.any() else 0.0)
    return out


F0_LO, F0_HI = 50.0, 4000.0
PITCH_WIN = 2048


def _acf_frames(mono):
    """分帧自相关（FFT 加速）-> (ac 帧×lag, lag_hz)。"""
    n = (len(mono) // HOP) * HOP
    if n < PITCH_WIN:
        return np.zeros((1, PITCH_WIN)), np.zeros(1)
    frames = mono[:n].reshape(-1, PITCH_WIN) if n % PITCH_WIN == 0 else \
        mono[np.arange(0, n - PITCH_WIN, HOP)[:, None] + np.arange(PITCH_WIN)[None, :]]
    f = np.fft.rfft(frames, n=2 * PITCH_WIN)
    ac = np.fft.irfft(f * np.conj(f), n=2 * PITCH_WIN)[:, :PITCH_WIN]
    return ac, ac[:, 0]


def _comb_tol(freqs, f0):
    """谐波容差：Hann 主瓣半宽（2 bin）与 1.5% f0 取大。"""
    df = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0
    return max(2.0 * df, 0.015 * f0)


def _harmonic_ratio(P, freqs, f0):
    """f0 的整数倍谐波族能量占比（bin 掩码去重）。"""
    if f0 <= 0:
        return 0.0
    total = float(P.sum()) + 1e-12
    sel = np.zeros(len(freqs), dtype=bool)
    tol = _comb_tol(freqs, f0)
    k = 1
    while k * f0 <= freqs[-1]:
        sel |= np.abs(freqs - k * f0) <= tol
        k += 1
    return round(float(P[sel].sum()) / total, 4)


def _peak_hz(P, freqs, i):
    """抛物线插值细化峰频（bin 量化误差约半 bin）。"""
    if i <= 0 or i >= len(P) - 1:
        return float(freqs[i])
    a, b, c = float(P[i - 1]), float(P[i]), float(P[i + 1])
    den = a - 2.0 * b + c
    d = 0.0 if den == 0 else 0.5 * (a - c) / den
    df = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0
    return float(freqs[i] + d * df)


def _spec_peaks(P, freqs, n=8, prom=PROM_MIN):
    """去趋势离散峰：局部极大且高出邻域中位数 prom 倍（噪声峰不过滤）。"""
    if P.size < 6:
        return []
    m = P[1:-1]
    idx = np.where((m > P[:-2]) & (m >= P[2:]) & (m > 0.02 * float(P.max())))[0] + 1
    out = []
    for i in idx:
        w = np.concatenate([P[max(1, i - 25):max(2, i - 2)],
                            P[min(len(P) - 2, i + 3):i + 25]])
        if w.size >= 4 and float(P[i]) > prom * float(np.median(w)):
            out.append((_peak_hz(P, freqs, int(i)), float(P[i])))
    out.sort(key=lambda t: -t[1])
    return [t[0] for t in out[:n]]


def _pitch(mono, sr, mag, freqs, flatness):
    """f0：离散谱峰＋ACF 子倍频候选 → 谐波能量占比校验；噪声/静音置 0。"""
    ac, base = _acf_frames(mono)
    lo, hi = int(sr / F0_HI), max(int(sr / F0_HI) + 1, int(sr / F0_LO))
    hi = min(hi, PITCH_WIN - 1)
    seg = ac[:, lo:hi + 1] / (base[:, None] + 1e-12)
    best = lo + np.argmax(seg, axis=1)
    conf = seg[np.arange(seg.shape[0]), best - lo]
    P = (mag ** 2).mean(axis=0)
    out = {"f0_hz": 0.0, "voiced_confidence": 0.0, "pitch_contour_std_cents": 0.0,
           "glissando_cents_per_s": 0.0, "inharmonicity": 1.0, "harmonic_ratio": 0.0}
    if float(flatness) > FLAT_TONAL:
        out["voiced_confidence"] = round(min(0.2, float(conf.mean()) * 0.2), 3)
        return out
    peaks = _spec_peaks(P, freqs)
    cands = list(peaks)
    c = sr / float(max(float(best.mean()), 1))
    while c >= F0_LO:
        if not any(abs(c - p) <= _comb_tol(freqs, c) for p in peaks):
            cands.append(c)
        c /= 2.0
    f0, ratio = 0.0, 0.0
    for c in cands:
        if c < F0_LO or c > min(F0_HI, float(freqs[-1])):
            continue
        tol = _comb_tol(freqs, c)
        if not any(abs(p - c) <= tol for p in peaks):
            continue
        r = _harmonic_ratio(P, freqs, c)
        if r < HARM_MIN:
            continue
        if f0 <= 0 or r > ratio + 0.05 or (r >= ratio - 0.05 and c < f0):
            f0, ratio = c, r
    out["f0_hz"] = round(f0, 1)
    out["harmonic_ratio"] = ratio
    if f0 <= 0:
        return out


    out["voiced_confidence"] = round((1.0 - float(flatness)) * min(1.0, ratio / 0.5), 3)
    lag = sr / f0
    w0, w1 = max(1, int(lag * 0.9)), min(PITCH_WIN - 1, int(lag * 1.1) + 1)
    if w1 <= w0:
        return out
    sub = ac[:, w0:w1 + 1] / (base[:, None] + 1e-12)
    bb = w0 + np.argmax(sub, axis=1)
    hit = sub[np.arange(sub.shape[0]), bb - w0]
    fv = (sr / bb.astype(np.float64))[hit > 0.35]
    if fv.size >= 3:
        cents = 1200.0 * np.log2(fv / fv[0])
        out["pitch_contour_std_cents"] = round(float(np.std(cents)), 1)
        hop_s = HOP / float(sr)
        out["glissando_cents_per_s"] = round(
            float(np.mean(np.abs(np.diff(cents)))) / hop_s, 1)
    return out

def _inharmonicity(mag, freqs, f0):
    """非谐波度 = 1 - 谐波族能量占比（与 harmonic_ratio 互补）。"""
    if f0 <= 0:
        return 1.0
    P = (mag ** 2).mean(axis=0)
    return round(1.0 - _harmonic_ratio(P, freqs, f0), 4)

def _hz2mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def _mel2hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


def mel_filterbank(sr, n_bins, n_mel=N_MEL, fmin=0.0, fmax=None):
    """numpy 手搓三角 mel 滤波器组 -> (n_mel, n_bins)。"""
    fmax = fmax or sr / 2.0
    pts = _mel2hz(np.linspace(_hz2mel(fmin), _hz2mel(fmax), n_mel + 2))
    fb = np.zeros((n_mel, n_bins), dtype=np.float64)
    bins = np.linspace(0.0, n_bins - 1, n_bins)
    idx = (freqs_to_bins(pts, sr, n_bins))
    for i in range(n_mel):
        left, mid, right = idx[i], idx[i + 1], idx[i + 2]
        if mid > left:
            sel = (bins >= left) & (bins <= mid)
            fb[i, sel] = (bins[sel] - left) / (mid - left)
        if right > mid:
            sel = (bins > mid) & (bins <= right)
            fb[i, sel] = (right - bins[sel]) / (right - mid)
    return np.clip(fb, 0.0, None)


def freqs_to_bins(hz_points, sr, n_bins):
    """rfft 频率点 -> bin 下标（线性）。"""
    nyq = sr / 2.0
    return np.clip(np.round(np.asarray(hz_points) / nyq * (n_bins - 1)), 0, n_bins - 1)


def _dct2(x, n_out):
    """手搓 DCT-II（取前 n_out 维）。"""
    k = np.arange(n_out)[:, None]
    m = np.arange(x.shape[1])[None, :]
    mat = np.cos(math.pi * k * (2 * m + 1) / (2.0 * x.shape[1]))
    mat = mat * np.sqrt(2.0 / x.shape[1])
    mat[0] = mat[0] / math.sqrt(2.0)
    return x @ mat.T


def mfcc(mag, sr, n_bins):
    """40 带 mel -> log -> DCT -> 13 维 MFCC 的均值与标准差。"""
    fb = mel_filterbank(sr, n_bins)
    mel_e = np.clip(mag @ fb.T, 1e-10, None)
    logm = np.log(mel_e)
    coefs = _dct2(logm, N_MFCC)
    return {"mfcc_mean": [round(float(v), 3) for v in coefs.mean(axis=0)],
            "mfcc_std": [round(float(v), 3) for v in coefs.std(axis=0)],
            "mel_energy_mean_db": [round(float(v), 2) for v in 10.0 * np.log10(mel_e.mean(axis=0))]}


def chroma(mag, freqs):
    """12 维音级强度（对数加权、按帧最大值归一）。"""
    out = np.zeros(12)
    sel = freqs > 0
    f, m = freqs[sel], mag[:, sel]
    pc = np.mod(np.round(12.0 * np.log2(np.maximum(f, 1e-6) / 440.0) + 69.0), 12).astype(int)
    for i in range(12):
        cols = pc == i
        if cols.any():
            out[i] = float(m[:, cols].sum(axis=1).max())
    peak = out.max()
    return [round(float(v / peak), 3) for v in out] if peak > 0 else [0.0] * 12


def _grid(mag, freqs, n_t=GRID_T, n_f=GRID_F):
    """16 时间帧 × 24 频段量化 ASCII 栅格（让模型「看见」声音形状）。"""
    n = mag.shape[0]
    cuts = np.linspace(0, n, n_t + 1).round().astype(int)
    edges = np.geomspace(max(freqs[1], 40.0), freqs[-1], n_f + 1)
    rows = []
    for i in range(n_t):
        lo = min(int(cuts[i]), n - 1)
        fr = mag[lo:max(int(cuts[i + 1]), lo + 1)]
        cells = []
        for j in range(n_f):
            sel = (freqs >= edges[j]) & (freqs < edges[j + 1])
            v = -9.0
            if sel.any():
                m = float(fr[:, sel].mean())
                v = float(np.log10(m + 1e-9).mean()) if m > 0 else -9.0
            cells.append(v)
        rows.append(np.array(cells))
    mat = np.vstack(rows)
    lo, hi = float(mat.min()), float(mat.max())
    span = hi - lo if hi > lo else 1.0
    q = np.clip(((mat - lo) / span * (len(RAMP) - 1)).round().astype(int), 0, len(RAMP) - 1)
    return ["".join(RAMP[v] for v in row) for row in q]


def _tokens(enc):
    """一行紧凑编码串（供 --tokens 与 prompt 摘要）。"""
    l, t, s, p = enc["loudness"], enc["time"], enc["spectral"], enc["pitch"]
    ch = ",".join(str(v) for v in enc["chroma"])
    return (f"A:RMS{l['rms_dbfs']:.0f}|CEN{s['spectral_centroid_hz']:.0f}"
            f"|F0={p['f0_hz']:.0f}|ON={t['onset_rate_hz']:.0f}"
            f"|FLAT{s['spectral_flatness']:.2f}|ZCR{t['zcr_mean']:.2f}"
            f"|DYN{l['dynamic_range_db']:.0f}|BPM{t['bpm']:.0f}|CHR[{ch}]")


def encode(mono, sr, bits, channels, src):
    """全特征编码（确定性）。"""
    mag, freqs = stft(mono, sr)
    env = _block_rms(mono, sr)
    meta = meta_feats(mono, sr, bits, channels)
    spec = _spec_moments(mag, freqs)
    enc = {"version": "ap-enc-1", "source": src, "meta": meta,
           "loudness": loudness_feats(mono, sr), "time": time_feats(mono, sr, env),
           "spectral": spec, "band_contrast": _band_contrast(mag, freqs),
           "mel": mfcc(mag, sr, mag.shape[1]),
           "pitch": _pitch(mono, sr, mag, freqs, spec["spectral_flatness"]),
           "chroma": chroma(mag, freqs)}
    enc["pitch"]["inharmonicity"] = _inharmonicity(mag, freqs, enc["pitch"]["f0_hz"])
    if meta["is_silence"]:
        _zero_spectral(enc)
    enc["spectrogram_grid"] = _grid(mag, freqs)
    enc["tokens"] = _tokens(enc)
    return enc


def _zero_spectral(enc):
    """静音：频域特征全置 0 并标 is_silence（空谱均值会误导判读）。"""
    for k in enc["spectral"]:
        enc["spectral"][k] = 0.0
    for k in ("f0_hz", "voiced_confidence", "harmonic_ratio",
              "pitch_contour_std_cents", "glissando_cents_per_s"):
        enc["pitch"][k] = 0.0
    enc["pitch"]["inharmonicity"] = 1.0
    enc["band_contrast"] = [0.0] * BANDS
    enc["chroma"] = [0.0] * 12
    enc["mel"] = {"mfcc_mean": [0.0] * N_MFCC, "mfcc_std": [0.0] * N_MFCC,
                  "mel_energy_mean_db": [0.0] * N_MEL}
    enc["time"]["onset_rate_hz"] = 0.0
    enc["time"]["bpm"] = 0.0

def render_text(enc):
    """人类可读文本块（含 ASCII 谱栅格，高频在上）。"""
    lines = [f"# 声音编码 {enc['version']}  source={enc['source'].get('file', '')}"]
    for key in ("meta", "loudness", "time", "spectral", "pitch"):
        lines.append(f"[{key}]")
        lines += [f"  {k}={v}" for k, v in enc[key].items()]
    lines.append(f"[band_contrast] {enc['band_contrast']}")
    lines.append(f"[mfcc_mean] {enc['mel']['mfcc_mean']}")
    lines.append(f"[mfcc_std] {enc['mel']['mfcc_std']}")
    lines.append(f"[chroma] {enc['chroma']}")
    lines.append("[spectrogram_grid] 16t x 24f (高频在上, 低频在下)")
    lines += ["  " + row for row in reversed(enc["spectrogram_grid"])]
    lines.append(f"[tokens] {enc['tokens']}")
    return "\n".join(lines)


def slice_span(mono, sr, start, end, max_sec):
    """按秒裁剪；跨度超 max_sec 时截断（确定性）。"""
    s = max(0, int(start * sr))
    e = len(mono) if end is None else min(len(mono), int(end * sr))
    cap = int(max_sec * sr)
    if e - s > cap:
        e = s + cap
    if e <= s:
        cli.die("裁剪后无样本：检查 --start/--end/--max-sec")
    return mono[s:e], s / float(sr), e / float(sr)


def encode_file(path, start=0.0, end=None, max_sec=10.0):
    """解码 + 裁剪 + 编码（供 perceive/batch 同进程复用）。"""
    mono, sr, ch, bits, _n = cli.read_wav(path)
    seg, s, e = slice_span(mono, sr, start, end, max_sec)
    src = {"file": os.path.basename(path), "start": round(s, 3), "end": round(e, 3),
           "max_sec": float(max_sec)}
    return encode(seg, sr, bits, ch, src)


def main(argv=None):
    ap = argparse.ArgumentParser(description="纯 numpy 声学编码器（声音编码）")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--max-sec", type=float, default=10.0)
    ap.add_argument("--format", choices=["text", "json", "tokens"], default="text")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    enc = encode_file(a.audio, a.start, a.end, a.max_sec)
    text = {"json": lambda: json.dumps(enc, ensure_ascii=False, indent=2),
            "tokens": lambda: enc["tokens"],
            "text": lambda: render_text(enc)}[a.format]()
    cli.emit(text, a.out)
    return 0


if __name__ == "__main__":
    import os
    raise SystemExit(main())
