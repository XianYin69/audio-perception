"""perceive - 声音编码 -> 网关文本判读（type/feeling/object/emotion/requirement）。

能力边界（诚实红线）：模型不"听"波形，只读数值编码＋ASCII 谱栅格做推理；
细粒度千类声事件不可靠，须降置信度并写进 uncertainty。api_key 绝不打印。
网关输出被 max_tokens 截断时先抢救（_salvage_json），救不回即标 parse_failed，
绝不拿空字段冒充正常结果。
"""
import argparse
import json
import re

import _cli as cli
import analyze

SCHEMA_KEYS = ["type", "feeling", "object", "emotion", "requirement",
               "evidence", "uncertainty", "audio_encoding_digest", "usage"]
RAW_KEEP = 4000

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
    "证据不足时 confidence<=0.5 并在 uncertainty 写明缺什么能力。\n"
    "输出预算（务必精简，超出即被截断）：feeling 不超过 6 个词；object.top3 恰好 3 项、"
    "每项 name 不超过 12 字；object.reasoning 不超过 120 字；evidence 不超过 6 条、"
    "每条 implies 不超过 40 字；uncertainty 不超过 3 条；"
    "audio_encoding_digest 与 usage 一律留空或省略（本地自填，不要回显）。\n"
    "类型硬要求：feeling 与 uncertainty 必须是 JSON 字符串数组（如 [\"尖锐\",\"持续\"]），不得写成一句话；evidence 必须是对象数组；"
    "top3 每项必须是 {\"name\":\"…\",\"confidence\":0.0} 对象。"
)
RETRY_HINT = "只输出压缩 JSON，evidence≤3 条，其余字段从简，不要代码围栏。"


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _closers(stack):
    """按未闭合栈生成补齐串（后开先闭）。"""
    return "".join("]" if b == "[" else "}" for b in reversed(stack))


def _scan(s):
    """括号平衡扫描：忽略字符串内括号与转义。

    -> (closed, end, cuts)：closed=顶层对象是否闭合；end=闭合下标；
    cuts=[(切点, 补齐串)]，切点都是「值已完整」的边界，按出现顺序。
    """
    stack = []
    in_str = esc = False
    cuts = []
    end = -1
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                cuts.append((i + 1, _closers(stack)))
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            if not stack:
                end = i if ch == "}" else end
                break
            cuts.append((i + 1, _closers(stack)))
        elif ch == "," and stack:
            cuts.append((i, _closers(stack)))
    return end >= 0, end, cuts


def _salvage_json(text):
    """截断抢救：剥围栏 -> 平衡扫描 -> 回退到最后完整值边界补齐后 loads。

    成功返回 dict（抢救件附 "truncated": true），彻底救不回返回 None。
    """
    body = FENCE.sub("", text or "").strip()
    start = body.find("{")
    if start < 0:
        return None
    frag = body[start:]
    closed, end, cuts = _scan(frag)
    tries = [frag[:end + 1]] if closed else []
    for pos, closers in reversed(cuts[-16:]):
        tries.append(frag[:pos].rstrip().rstrip(",") + closers)
    for cand in tries:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj:
            if not closed:
                obj["truncated"] = True
            return obj
    return None


def parse_reply(text):
    """剥围栏解析；完整 JSON 优先，被截断则抢救。返回 (dict|None, truncated)。"""
    obj = _salvage_json(text)
    if isinstance(obj, dict) and obj:
        return obj, bool(obj.get("truncated"))
    return None, False


def _as_list(val, seps):
    """数组字段容错：模型常把列表写成一句话，按分隔符拆而非丢弃。"""
    if isinstance(val, list):
        return [v for v in val if not (isinstance(v, str) and not v.strip())]
    if isinstance(val, str) and val.strip():
        return [p.strip(" 。.") for p in re.split(seps, val.strip()) if p.strip(" 。.")]
    return []


def normalize(obj, enc, model, usage, raw="", truncated=False):
    """补齐固定键；缺项填空而非猜测（不夸大识别率）。

    解析彻底失败：写 parse_failed=true 并保留 raw 全文（截 RAW_KEEP 字），
    不得用空字段冒充正常结果。
    """
    ok = isinstance(obj, dict)
    out = {k: obj.get(k) if ok else None for k in SCHEMA_KEYS}
    for k, default in (("type", {"primary": "", "sub": "", "confidence": 0.0}),
                       ("object", {"top3": [], "reasoning": ""}),
                       ("emotion", {"primary": "", "intensity": 0.0, "secondary": ""}),
                       ("requirement", {"action": "", "urgency": "low", "rationale": ""})):
        if not isinstance(out[k], dict):
            out[k] = default
    out["feeling"] = _as_list(out["feeling"], r"[、，,;；\s]+")[:6]
    out["uncertainty"] = _as_list(out["uncertainty"], r"[、，,;；\n]+")[:3]
    out["evidence"] = _as_list(out["evidence"], r"[;；\n]+")[:6]
    out["audio_encoding_digest"] = out.get("audio_encoding_digest") or enc["tokens"]
    out["usage"] = {"model": model, "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0))}
    if truncated:
        out["truncated"] = True
    if not ok:
        out["parse_failed"] = True
        out["raw"] = (raw or "")[:RAW_KEEP]
    return out


def perceive(enc, hint=None, max_tokens=2048):
    """编码 -> 网关判读。

    一次调用；唯一例外：finish_reason=="length" 且抢救失败时，追加压缩指令重试一次
    （见 resistance/失败即停不重试）。其余失败一律即停。
    """
    user = f"声音编码：\n{analyze.render_text(enc)}"
    if hint:
        user += f"\n用户先验提示：{hint}"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    res = cli.chat_text(msgs, max_tokens=max_tokens)
    obj, trunc = parse_reply(res["reply"])
    if obj is None and res.get("finish_reason") == "length":
        res = cli.chat_text(msgs + [{"role": "user", "content": RETRY_HINT}],
                            max_tokens=max_tokens)
        obj, trunc = parse_reply(res["reply"])
    return normalize(obj, enc, res["model"], res["usage"],
                     raw=res["reply"], truncated=trunc)


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
    ap.add_argument("--max-tokens", type=int, default=2048)
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
