"""batch - 目录批量：逐文件编码+判读，汇总 JSON 表与一行摘要。

失败即停不重试：单文件失败记入 errors 并继续下一个（不重复调用网关）。
产物落工作区 tmp。
"""
import argparse
import json
import os
import sys

import _cli as cli
import analyze
import perceive

EXTS = (".wav",)


def collect(dirpath, recursive=False):
    """收集 WAV 文件（按名排序，确定性）。"""
    out = []
    if recursive:
        for root, _dirs, files in os.walk(dirpath):
            out += [os.path.join(root, f) for f in files
                    if f.lower().endswith(EXTS)]
    else:
        out = [os.path.join(dirpath, f) for f in sorted(os.listdir(dirpath))
               if f.lower().endswith(EXTS)]
    return sorted(out)


def run(files, max_sec=10.0, hint=None, use_gateway=True):
    """逐文件处理 -> (rows, errors)。"""
    rows, errors = [], []
    for path in files:
        name = os.path.basename(path)
        try:
            enc = analyze.encode_file(path, 0.0, None, max_sec)
        except SystemExit:
            errors.append({"file": name, "error": "decode/encode failed"})
            continue
        row = {"file": name, "tokens": enc["tokens"],
               "duration": enc["meta"]["duration"],
               "centroid": enc["spectral"]["spectral_centroid_hz"],
               "f0": enc["pitch"]["f0_hz"], "flatness": enc["spectral"]["spectral_flatness"]}
        if use_gateway:
            res = perceive.perceive(enc, hint)
            row["type"] = res["type"]
            row["object"] = (res["object"].get("top3") or [{}])[0].get("name", "")
            row["emotion"] = res["emotion"].get("primary", "")
        rows.append(row)
    return rows, errors


def summary(rows, errors):
    """一行摘要。"""
    return (f"共 {len(rows)} 个文件，失败 {len(errors)} 个；"
            f"类型分布 " + json.dumps(_tally(rows), ensure_ascii=False))


def _tally(rows):
    tally = {}
    for r in rows:
        key = (r.get("type") or {}).get("primary", "encoding-only")
        tally[key] = tally.get(key, 0) + 1
    return tally


def main(argv=None):
    ap = argparse.ArgumentParser(description="目录批量声音判读")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--max-sec", type=float, default=10.0)
    ap.add_argument("--hint", default=None)
    ap.add_argument("--no-gateway", action="store_true", help="只编码不调网关")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if not os.path.isdir(a.dir):
        cli.die(f"目录不存在：{a.dir}")
    files = collect(a.dir, a.recursive)
    if not files:
        cli.die(f"目录内无 WAV 文件：{a.dir}（非 WAV 请先转码，见 knowledge/WAV解码注意.md）")
    rows, errors = run(files, a.max_sec, a.hint, use_gateway=not a.no_gateway)
    payload = json.dumps({"dir": os.path.abspath(a.dir), "count": len(rows),
                          "results": rows, "errors": errors,
                          "summary": summary(rows, errors)},
                         ensure_ascii=False, indent=2)
    cli.emit(payload, a.out)
    print(summary(rows, errors), file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
