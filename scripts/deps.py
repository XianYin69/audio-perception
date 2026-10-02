"""deps - 依赖守门：缺包只报错并给出手动安装建议，绝不自动安装。"""
import importlib
import sys

TAG = "[audio-perception]"
SUGGEST = {"numpy": "numpy", "sounddevice": "sounddevice", "pyaudio": "pyaudio"}


def require(modules, optional=False):
    """返回缺失模块名列表；硬依赖缺失时 exit 2（红线：不自动 pip）。"""
    missing = []
    for name in modules:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing and not optional:
        pkgs = " ".join(SUGGEST.get(m, m) for m in missing)
        print(f"{TAG} 缺少依赖: {', '.join(missing)}\n"
              f"{TAG} 请自行确认后手动执行: python -m pip install {pkgs}\n"
              f"{TAG} 本技能不自动安装任何依赖。", file=sys.stderr)
        sys.exit(2)
    return missing


def have(module):
    """探测可选模块是否可用（capture.py 用）。"""
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False
