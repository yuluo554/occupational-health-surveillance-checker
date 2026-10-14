#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""演示素材生成器（M5-11，程序化产出，**两次生成 sha256 逐个一致**）。

产出 docs/assets/：
    gui-tab-1-selfcheck.png … gui-tab-6-report.png   GUI 六页签实图（offscreen 渲染）
    gui-demo.gif                                     六页签轮播 GIF

确定性纪律（NFR-4）：
  * offscreen 平台 + 固定窗口尺寸；不读系统时钟进产物；
  * GIF 由 Pillow 以固定参数编码（GIF 格式无时间戳元数据）；
  * 演示数据来自冻结真值库/合成规则集（无真实劳动者信息）。

用法：
    py -3.12 tools/gen_demo_assets.py            # 生成
    py -3.12 tools/gen_demo_assets.py --check    # 再生成并断言 sha256 逐个一致
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "assets"
)

# 固定渲染参数（确定性：窗口尺寸/页签次序/帧延时全部写死）
WINDOW_W, WINDOW_H = 1120, 720
FRAME_DELAY_MS = 1600
TAB_KEYS = (
    "1-selfcheck",
    "2-plan",
    "3-check",
    "4-scan",
    "5-compare",
    "6-report",
)


def _ensure_qt_env():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("OHSCHECK_GUI_SMOKE", "")


def _load_cjk_font(app):
    """offscreen 平台不带字体数据库 → 显式加载系统中文字体文件。

    固定候选列表（Windows 自带，取第一个存在的）：同机同文件 → 渲染确定。
    """
    from PySide6.QtGui import QFont, QFontDatabase

    candidates = (
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",    # 黑体
        "C:/Windows/Fonts/simsun.ttc",    # 宋体
    )
    for font_path in candidates:
        if not os.path.isfile(font_path):
            continue
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
            return families[0]
    return None


def _render_tab_pngs(out_dir):
    """GUI 六页签逐页 grab → PNG 字节列表（顺序与 TAB_KEYS 一致）。"""
    _ensure_qt_env()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ohscheck.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    _load_cjk_font(app)
    window = MainWindow(None)
    window.resize(WINDOW_W, WINDOW_H)
    window.show()

    tabs = window.centralWidget()
    images = []

    def grab_current():
        pix = window.grab()
        buf = _pixmap_to_png_bytes(pix)
        images.append(buf)

    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        app.processEvents()
        QTimer.singleShot(0, app.quit)  # 清残留事件
        app.processEvents()
        _trigger_demo_action(app, tabs.widget(index), index)
        grab_current()

    window.close()
    return images


def _click_button(page, index=0):
    """点击页内第 index 个 QPushButton（演示动作统一走按钮，不注入内部状态）。"""
    from PySide6.QtWidgets import QPushButton

    buttons = page.findChildren(QPushButton)
    if index < len(buttons):
        buttons[index].click()


def _mini_records_dir(records):
    """复制前 4 件真值档案到确定性临时目录（演示批量页用，避免整库拖住事件循环）。"""
    import shutil
    import tempfile

    if not records or not os.path.isdir(records):
        return None
    names = sorted(n for n in os.listdir(records) if n.endswith(".json"))[:4]
    if not names:
        return None
    demo_dir = os.path.join(tempfile.gettempdir(), "ohscheck-demo-records")
    if os.path.isdir(demo_dir):
        shutil.rmtree(demo_dir)
    os.makedirs(demo_dir)
    for name in names:
        shutil.copyfile(os.path.join(records, name), os.path.join(demo_dir, name))
    return demo_dir


def _trigger_demo_action(app, page, index):
    """每页截图前的取数动作（按下主按钮让页签展示真实引擎输出）。

    逐页语义：
      0 自检：执行自检；1 岗位应检：粘贴示例画像后推导；
      2 档案核查：粘贴真值件后核查；3 批量扫描：扫真值库目录；
      4 版本对照：载入规则集 + 对照；5 报告导出：填真值件路径（不落盘演示）。
    """
    import json
    import os

    from ohscheck import paths

    root = paths.find_data_dir(None)
    records = os.path.join(root, "truth", "records") if root else None
    first_record = None
    if records and os.path.isdir(records):
        for name in sorted(os.listdir(records)):
            if name.endswith(".json"):
                first_record = os.path.join(records, name)
                break

    from PySide6.QtWidgets import QLineEdit

    edits = page.findChildren(QLineEdit)

    if index == 0:
        _click_button(page, 0)
    elif index == 1 and edits:
        # 按钮 0 是"载入文件…"（模态对话框会阻塞 offscreen 演示）→ 只按主按钮
        profile = {
            "position_id": "POS-DEMO-001",
            "exam_date": "2026-09-15",
            "factors": [{"factor_code": "GBZ188-5.19"}],
        }
        edits[0].setText(json.dumps(profile, ensure_ascii=False))
        _click_button(page, 1)
    elif index == 2 and edits and first_record:
        with open(first_record, "r", encoding="utf-8") as fh:
            edits[0].setText(fh.read())
        _click_button(page, 1)
    elif index == 3 and edits and records:
        # 演示取 4 件档案的小目录（批量整库 72 件会拖住事件循环）
        demo_dir = _mini_records_dir(records)
        if demo_dir:
            edits[0].setText(demo_dir)
            _click_button(page, 2)
    elif index == 4:
        # 无按钮序号歧义：0=载入可用规则集，1=对照
        _click_button(page, 0)
        app.processEvents()
        _click_button(page, 1)
    elif index == 5 and edits and first_record:
        edits[2].setText(first_record)  # 单件档案
        edits[5].setText("2026-10-14T00:00:00")  # 生成时间（注入，可复现）
        # 不点导出按钮——演示帧只展示输入态，避免演示运行写盘
    app.processEvents()


def _pixmap_to_png_bytes(pixmap):
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    return bytes(buf.data())


def _pngs_to_gif(png_bytes_list, out_path):
    """PNG 帧序列 → 轮播 GIF（Pillow 固定参数；确定性由同输入同字节保证）。"""
    from io import BytesIO

    from PIL import Image

    frames = [Image.open(BytesIO(data)).convert("P", palette=Image.WEB) for data in png_bytes_list]
    head, tail = frames[0], frames[1:]
    head.save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=tail,
        duration=FRAME_DELAY_MS,
        loop=0,
        optimize=False,
    )
    return out_path


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _write_manifest(out_dir, digests):
    lines = []
    for name in sorted(digests):
        lines.append("%s  %s" % (digests[name], name))
    text = "\n".join(lines) + "\n"
    path = os.path.join(out_dir, "sha256sums.txt")
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))
    digests["sha256sums.txt"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digests


def generate(out_dir=ASSETS_DIR):
    out_dir = os.path.abspath(out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    images = _render_tab_pngs(out_dir)
    digests = {}
    for key, data in zip(TAB_KEYS, images):
        name = "gui-tab-%s.png" % key
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    gif_path = os.path.join(out_dir, "gui-demo.gif")
    _pngs_to_gif(images, gif_path)
    digests["gui-demo.gif"] = _sha256(gif_path)
    _write_manifest(out_dir, digests)
    return digests


def check():
    """再生成到临时目录，断言与现存产物 sha256 逐个一致。"""
    import shutil
    import tempfile

    if not os.path.isdir(ASSETS_DIR):
        return False, "产物目录不存在：%s" % ASSETS_DIR
    tmp = tempfile.mkdtemp(prefix="ohscheck-demo-")
    try:
        fresh = generate(out_dir=tmp)
        for name, digest in sorted(fresh.items()):
            existing = os.path.join(ASSETS_DIR, name)
            if not os.path.isfile(existing):
                return False, "缺少产物：%s" % name
            if _sha256(existing) != digest:
                return False, "sha256 不一致：%s" % name
        return True, "DEMO_ASSETS_OK（%d 个文件 sha256 逐个一致）" % len(fresh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    if "--check" in argv:
        ok, message = check()
        print(message)
        return 0 if ok else 1
    digests = generate()
    for name in sorted(digests):
        print("%s  %s" % (digests[name], name))
    print("DEMO_ASSETS_OK（已写入 docs/assets/）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
