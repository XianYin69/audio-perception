"""perceive - 声音编码 -> 网关文本判读（type/feeling/object/emotion/requirement）。

能力边界（诚实红线）：模型不"听"波形，只读数值编码＋ASCII 谱栅格做推理；
细粒度千类声事件不可靠，须降置信度并写进 uncertainty。api_key 绝不打印。
"""
import argparse
import json
import re

import _cli as cli
import analyze

SCHEMA_KEYS = ["type", "feeling", "object", "emotion", "requirement",
               "evidence", "uncertainty", "audio_encoding_digest", "usage"]

SYSTEM = (
    "你是声音判读器。输入不是音频，而是确定性声学编码（数值特征＋16x24 ASCII 谱栅格，"
    "栅格高频在上、时间从左到右）。你只能据此推理，不得声称你听到了声音。\n"
    "类别体系（primary 只能从中选）：语音、音乐、动物、自然、交通载具、机械工具、"
    "冲击碰撞、电子提示音、警报、环境底噪、人声非语言、爆炸枪声、流体、摩擦接触。\n"
    "判别锚点：语音=谐波+2-4kHz 共振峰+音节起音 3-8Hz；警报=稳周期 0.5-2Hz 调制+"
    "窄带高质心；撞击=毫秒级起音+宽频+指数衰减；鸟鸣=2-8kHz 快调频谐波；"
    "风=低频宽谱无谐波+高平坦度；引擎=低基频+整数谐波族+慢漂移；"
    "玻璃/金属摩擦=极高质心+窄带+强谐波；音乐=稳定 f0+谐波族+节拍 BPM 稳定。\n"
    "情绪只能由声学线索推（响度、动态、起音快慢、音高轮廓、协和度），不得臆测语义。\n"
    "只输出一个 JSON 对象，不要解释、不要代码围栏，键固定为："
    "type{primary,sub,confidence}, feeling[str], object{top3[{name,confidence}],reasoning}, "
    "emotion{primary,intensity,secondary}, requirement{action,urgency(low|mid|high),rationale}, "
    "evidence[{feature,value,implies}], uncertainty[str], audio_encoding_digest, usage{model,"
    "prompt_tokens,completion_tokens}。confidence/intensity 为 0-1 小数；"
    "证据不足时 confidence<=0.5 并在 uncertainty 写明缺什么能力。"
)


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_reply(text):
    """剥围栏解析 JSON；失败再试一次（取首个 {...}），仍失败返回 None。"""
    for cand in (FENCE.sub("", text).strip(), _first_obj(text)):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _first_obj(text):
    """截取第一个平衡大括号片段。"""
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def normalize(obj, enc, model, usage):
    """补齐固定键；缺项填空而非猜测（不夸大识别率）。"""
    out = {k: obj.get(k) if isinstance(obj, dict) else None for k in SCHEMA_KEYS}
    for k, default in (("type", {"primary": "", "sub": "", "confidence": 0.0}),
                       ("object", {"top3": [], "reasoning": ""}),
                       ("emotion", {"primary": "", "intensity": 0.0, "secondary": ""}),
                       ("requirement", {"action": "", "urgency": "low", "rationale": ""})):
        if not isinstance(out[k], dict):
            out[k] = default
    for k, default in (("feeling", []), ("evidence", []), ("uncertainty", [])):
        if not isinstance(out[k], list):
            out[k] = default
    out["audio_encoding_digest"] = out.get("audio_encoding_digest") or enc["tokens"]
    out["usage"] = {"model": model, "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0))}
    if not isinstance(obj, dict):
        out["raw"] = obj
    return out


def perceive(enc, hint=None, max_tokens=1024):
    """编码 -> 网关判读（一次调用，失败即停）。"""
    user = f"声音编码：\n{analyze.render_text(enc)}"
    if hint:
        user += f"\n用户先验提示：{hint}"
    res = cli.chat_text([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}], max_tokens=max_tokens)
    parsed = parse_reply(res["reply"])
    return normalize(parsed if parsed is not None else res["reply"], enc,
                     res["model"], res["usage"])


def load_encoding(path):
    """读已存编码 JSON（analyze --format json 产物）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            enc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        cli.die(f"编码文件不可用 {path}: {exc}")
    if "tokens" not in enc or "spectral" not in enc:
        cli.die("编码文件缺 tokens/spectral 字段，非 ap-enc-1 产物")
    return enc


def main(argv=None):
    ap = argparse.ArgumentParser(description="声音编码 -> 网关判读")
    ap.add_argument("--audio")
    ap.add_argument("--encoding", help="复用 analyze --format json 产出的编码文件")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--max-sec", type=float, default=10.0)
    ap.add_argument("--hint", default=None)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--out", default=None)
    ap.add_argument("--raw", action="store_true", help="附带网关原始回复")
    a = ap.parse_args(argv)
    if not a.audio and not a.encoding:
        cli.die("必须给 --audio 或 --encoding 之一")
    enc = load_encoding(a.encoding) if a.encoding else analyze.encode_file(
        a.audio, a.start, a.end, a.max_sec)
    result = perceive(enc, a.hint, a.max_tokens)
    if a.raw:
        result["raw_reply"] = result.get("raw", "")
    cli.emit(json.dumps(result, ensure_ascii=False, indent=2), a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
