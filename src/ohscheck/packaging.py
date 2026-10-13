"""打包辅助（放**包内**，不占仓库顶层名——决策 D-15）。

顶层 `packaging.py` 会遮蔽 PyPI 的 `packaging`，而 PyInstaller 自身依赖它做版本判断，
构建会崩且报错指向莫名其妙处；包内命名空间不共享，故放这里。

本模块同时是"数据白名单"的**单一事实源**（M5 起生效）：
build_datas() 产出 datas 列表，spec 文本守门测试断言 spec 无手写数据路径。
"""

from __future__ import annotations

import os

# 打包数据的白名单（相对仓库根的路径 → dist 内目标路径）
DATA_WHITELIST = (
    ("data/rules", "data/rules"),
)

# 禁区段：版权原文快照一律不入包（M1 建库后生效）
FORBIDDEN_DATA_PREFIXES = (
    "data/knowledge/raw",
    "data/**/_private",
)


def is_frozen():
    """是否运行在 PyInstaller 冻结态。"""
    import sys

    return bool(getattr(sys, "frozen", False))


def build_datas():
    """构建 datas 列表（**白名单单一事实源**）。

    Returns:
        [(src_abs, dest_rel), ...]

    Raises:
        RuntimeError: 白名单里出现禁区段。
    """
    from . import paths

    root = _repo_root()
    out = []
    for src_rel, dest_rel in DATA_WHITELIST:
        for prefix in FORBIDDEN_DATA_PREFIXES:
            if src_rel.startswith(prefix.replace("/**", "")) or src_rel.startswith(prefix):
                raise RuntimeError("打包白名单含禁区段：%s" % src_rel)
        src_abs = os.path.join(root, src_rel)
        if not os.path.isdir(src_abs):
            raise RuntimeError("白名单数据目录不存在：%s" % src_abs)
        out.append((src_abs, dest_rel))
    return out


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
        if os.path.exists(os.path.join(cur, "pyproject.toml")):
            return cur
    raise RuntimeError("未定位到仓库根（未找到 pyproject.toml）")
