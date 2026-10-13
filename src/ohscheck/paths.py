"""数据目录定位（源码态 / 冻结态分支）。

优先级（决策 D-36，改优先级属"动了会打挂测试"的口径变更，配分支测试锁死）：
    1. 显式参数
    2. 环境变量 OHSCHECK_DATA_DIR
    3. 冻结态：sys._MEIPASS/data → exe目录/_internal/data（PyInstaller 6）
               → exe目录/data（兼容平铺布局）
    4. 源码态：从包 __file__ 上溯至含 pyproject.toml 的仓库根 → data/
"""

from __future__ import annotations

import os
import sys

ENV_DATA_DIR = "OHSCHECK_DATA_DIR"

_MARKERS = ("pyproject.toml", "plan")


def is_frozen():
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def exe_dir():
    """可执行文件所在目录；源码态返回 None。"""
    if not is_frozen():
        return None
    return os.path.dirname(os.path.abspath(sys.executable))


def _meipass_dir():
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    return os.path.abspath(base)


def frozen_data_candidates():
    """冻结态候选数据目录（按优先级）。"""
    out = []
    meipass = _meipass_dir()
    if meipass:
        out.append(os.path.join(meipass, "data"))
    ed = exe_dir()
    if ed:
        out.append(os.path.join(ed, "_internal", "data"))
        out.append(os.path.join(ed, "data"))
    return out


def source_data_candidates():
    """源码态候选数据目录：从包位置逐级上溯。"""
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    cur = here
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
        if any(os.path.exists(os.path.join(cur, m)) for m in _MARKERS):
            out.append(os.path.join(cur, "data"))
    return out


def find_data_dir(explicit=None):
    """定位 data/ 目录。找不到返回 None（由调用方转成 InputError）。"""
    if explicit:
        return os.path.abspath(explicit)

    env = os.environ.get(ENV_DATA_DIR)
    if env:
        return os.path.abspath(env)

    candidates = frozen_data_candidates() if is_frozen() else source_data_candidates()
    for cand in candidates:
        if os.path.isdir(cand):
            return os.path.abspath(cand)
    return None


def data_subdir(name, explicit=None, must_exist=True):
    """取 data/ 下的子目录（如 rules / truth / benchmark）。"""
    root = find_data_dir(explicit)
    if root is None:
        return None
    path = os.path.join(root, name)
    if must_exist and not os.path.isdir(path):
        return None
    return path


def data_file(*parts, **kwargs):
    """取 data/ 下的文件路径。"""
    root = find_data_dir(kwargs.get("explicit"))
    if root is None:
        return None
    path = os.path.join(root, *parts)
    if kwargs.get("must_exist", True) and not os.path.isfile(path):
        return None
    return path


def data_dir_is_inside(target, container):
    """冻结态自检用：target 是否落在 container 之内（决策 D-37）。

    非冻结态由调用方跳过；跨盘符时 os.path.commonpath 抛 ValueError → 视为不在内。
    """
    if not target or not container:
        return None
    try:
        target = os.path.abspath(target)
        container = os.path.abspath(container)
        return os.path.commonpath([target, container]) == container
    except ValueError:
        return False


def describe_search():
    """data/ 定位的诊断信息（selfcheck 用，便于排查冻结态问题）。"""
    info = {
        "frozen": is_frozen(),
        "executable": sys.executable,
        "package_file": os.path.abspath(__file__),
        "env_data_dir": os.environ.get(ENV_DATA_DIR),
        "candidates": frozen_data_candidates() if is_frozen() else source_data_candidates(),
    }
    info["resolved"] = find_data_dir()
    return info
