#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PyInstaller spec 生成器（M5-7：**datas 白名单单一事实源**的落盘出口）。

spec 文件本身入仓（`.gitignore` 对 `tools/*.spec` 例外放行），但**禁止手改**——
唯一写入者是本脚本；`--check` 再生成逐字节一致（gen_* 家族惯例，决策 D-26）。

datas 来源是 `ohscheck.packaging.DATA_WHITELIST`（单一事实源）：
    py -3.12 tools/gen_spec.py            # 生成 tools/packaging.spec
    py -3.12 tools/gen_spec.py --check    # 再生成并断言逐字节一致

构建（发布构建固定 3.12 通道，决策 D-14；PyInstaller ≥6 是打 GUI 的硬下限）：
    py -3.12 -m PyInstaller tools/packaging.spec

产物（onedir 双 exe，FR-G4）：
    dist/ohscheck/ohscheck-gui.exe   桌面界面（console=False）
    dist/ohscheck/ohscheck-cli.exe   命令行（console=True）
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ohscheck.loaders import write_bytes_lf  # noqa: E402
from ohscheck.packaging import DATA_WHITELIST  # noqa: E402

SPEC_NAME = "packaging.spec"

# datas 单一事实源 → spec 文本（M5-7：禁手写数据路径进 spec）。
# 白名单是仓库根相对路径；spec 由 PyInstaller 以其所在目录解析，
# 故在模板里用 SPECPATH 拼回仓库根绝对路径。
DATAS_LINES = "\n".join(
    "    (os.path.join(_ROOT, r'%s'), r'%s')," % (src.replace("\\", "/"), dest.replace("\\", "/"))
    for src, dest in DATA_WHITELIST
)

SPEC_TEMPLATE = """# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec（onedir 双 exe，FR-G4）——**生成文件，禁手改**。
# 唯一写入者：tools/gen_spec.py（datas 白名单单一事实源 = ohscheck.packaging.DATA_WHITELIST）。
# 再生成：py -3.12 tools/gen_spec.py --check
# 构建：py -3.12 -m PyInstaller tools/packaging.spec（发布构建固定 3.12 通道，决策 D-14）

import os

_ROOT = os.path.dirname(SPECPATH)
_ENTRY = lambda name: os.path.join(_ROOT, "src", "ohscheck", name)

datas = [
%(datas_lines)s
]

gui = Analysis(
    [_ENTRY("gui_entry.py")],
    pathex=[os.path.join(_ROOT, "src")],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz_gui = PYZ(gui.pure)

exe_gui = EXE(
    pyz_gui,
    gui.scripts,
    [],
    exclude_binaries=True,
    name="ohscheck-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
cli = Analysis(
    [_ENTRY("cli_entry.py")],
    pathex=[os.path.join(_ROOT, "src")],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz_cli = PYZ(cli.pure)

exe_cli = EXE(
    pyz_cli,
    cli.scripts,
    [],
    exclude_binaries=True,
    name="ohscheck-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe_gui,
    gui.binaries,
    gui.zipfiles,
    gui.datas,
    exe_cli,
    cli.binaries,
    cli.zipfiles,
    cli.datas,
    strip=False,
    upx=False,
    name="ohscheck",
)
"""


def spec_text():
    return SPEC_TEMPLATE % {"datas_lines": DATAS_LINES}


def spec_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, SPEC_NAME)


def generate():
    write_bytes_lf(spec_path(), spec_text().encode("utf-8"))
    return spec_path()


def check():
    """再生成断言逐字节一致（gen_* 家族守门）。"""
    path = spec_path()
    expected = spec_text()
    if not os.path.isfile(path):
        return False, "spec 文件不存在：%s" % path
    with open(path, "rb") as fh:
        actual = fh.read().decode("utf-8")
    if actual != expected:
        return False, "spec 与再生成结果不一致（被手改或白名单变了未重生成）"
    return True, "SPEC_OK"


def _ensure_utf8_stdio():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if not encoding or "utf" in encoding:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main(argv):
    _ensure_utf8_stdio()
    check_only = "--check" in argv
    if check_only:
        ok, message = check()
        print(message)
        return 0 if ok else 1
    path = generate()
    print("已生成 %s（datas 白名单 %d 项，来源 ohscheck.packaging.DATA_WHITELIST）"
          % (path, len(DATA_WHITELIST)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
