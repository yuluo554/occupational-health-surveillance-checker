"""GUI 主窗口：六页签装配（FR-G2）。

本模块是 PySide6 重件入口——只准被 `cli.cmd_gui` 的惰性 try 整段包住调用
（决策 D-38），自身不再对外暴露 defused 路径。

页签（plan/05 M5-2）：
    自检 / 岗位应检 / 档案核查 / 批量扫描 / 版本对照 / 报告导出
"""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QStatusBar, QTabWidget

from .pages import (
    check_page,
    compare_page,
    plan_page,
    report_page,
    scan_page,
    selfcheck_page,
)
from .service import Service

PAGE_BUILDERS = (
    ("自检", selfcheck_page.build),
    ("岗位应检", plan_page.build),
    ("档案核查", check_page.build),
    ("批量扫描", scan_page.build),
    ("版本对照", compare_page.build),
    ("报告导出", report_page.build),
)


def build_app(data_dir=None):
    """构造主窗口（cmd_gui 的唯一调用点）。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = MainWindow(data_dir)
    window.show()
    return app, window


class MainWindow(QMainWindow):
    """六页签主窗口；状态栏显示数据目录与冻结态。"""

    def __init__(self, data_dir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle("职业健康监护合规核查工作台（ohscheck）")
        self.service = Service(data_dir)

        tabs = QTabWidget()
        for title, builder in PAGE_BUILDERS:
            tabs.addTab(builder(self.service), title)
        self.setCentralWidget(tabs)

        status = QStatusBar()
        frozen = "冻结态" if _frozen_flag() else "源码态"
        data_display = data_dir or "自动定位"
        status.showMessage(f"数据目录：{data_display}（{frozen}）")
        self.setStatusBar(status)


def _frozen_flag():
    from .service import is_frozen

    return is_frozen()


def main(data_dir=None):
    """事件循环入口（退出码 0/1 交还 CLI 契约）。"""
    from PySide6.QtCore import QTimer

    app, _window = build_app(data_dir)
    # 非交互环境（offscreen 冒烟）下给出自动退出通道。
    if _auto_quit_requested():
        QTimer.singleShot(0, app.quit)
    return app.exec()


def _auto_quit_requested():
    import os

    return bool(os.environ.get("OHSCHECK_GUI_SMOKE"))
