"""CLI 冻结态入口（PyInstaller cli 的薄封装，FR-G4）。

与 `python -m ohscheck` 同语义：退出码契约一致（0/1/2/3）。
"""

import multiprocessing
import sys


def _main():
    from ohscheck.cli import main

    return main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(_main())
