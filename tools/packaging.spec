# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec（onedir 双 exe，FR-G4）——**生成文件，禁手改**。
# 唯一写入者：tools/gen_spec.py（datas 白名单单一事实源 = ohscheck.packaging.DATA_WHITELIST）。
# 再生成：py -3.12 tools/gen_spec.py --check
# 构建：py -3.12 -m PyInstaller tools/packaging.spec（发布构建固定 3.12 通道，决策 D-14）

import os

_ROOT = os.path.dirname(SPECPATH)
_ENTRY = lambda name: os.path.join(_ROOT, "src", "ohscheck", name)

datas = [
    (os.path.join(_ROOT, r'data/rules'), r'data/rules'),
    (os.path.join(_ROOT, r'data/benchmark'), r'data/benchmark'),
    (os.path.join(_ROOT, r'data/truth'), r'data/truth'),
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
