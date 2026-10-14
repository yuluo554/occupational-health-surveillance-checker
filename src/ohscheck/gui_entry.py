"""GUI 冻结态入口（PyInstaller gui 的薄封装，FR-G4）。

不进 CLI 参数解析；窗口版（console=False）无 stdout，任何失败都不能依赖
控制台呈现——数据缺失等错误由界面自身的自检页与退出码承载。
"""

import multiprocessing
import sys


def _main():
    from ohscheck.cli import _ensure_utf8_stdio
    from ohscheck.gui.main_window import main

    _ensure_utf8_stdio()
    return main(None)


if __name__ == "__main__":
    # PyInstaller onedir + Qt：子进程安全起见固定 spawn 语义。
    multiprocessing.freeze_support()
    sys.exit(_main())
