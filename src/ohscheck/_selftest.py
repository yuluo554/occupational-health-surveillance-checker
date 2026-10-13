"""冻结态自检（FR-G5 / 决策 D-37）。

结论写文件回传——窗口版 exe（console=False）无 stdout，这是唯一能脚本化验收的通路。

自检项：
  1. 数据目录定位（冻结态断言**落在 exe 目录内**；非冻结态该返回 None 不报 FAIL）
  2. 规则库加载 + 门控计数
  3. 引擎全链路（合成夹具驱动）
  4. 内置基准
结论 JSON：{frozen, data_dir, data_dir_inside_exe, rulesets, engine_ok, bench_ok, ok, exit_code}
"""

from __future__ import annotations

import json
import os
import sys


def _write_result(out_path, payload):
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).replace("\r\n", "\n")
    with open(out_path, "wb") as fh:
        fh.write((text + "\n").encode("utf-8"))


def run_selftest(out_path, data_dir=None):
    """执行自检并写结论文件；返回退出码。"""
    from . import __version__, paths
    from .errors import EXIT_OK, EXIT_USAGE

    payload = {
        "version": __version__,
        "python": sys.version.split()[0],
        "frozen": paths.is_frozen(),
        "executable": sys.executable,
        "data_dir": None,
        "data_dir_inside_exe": None,
        "rulesets": [],
        "engine_ok": False,
        "bench_ok": False,
        "ok": False,
    }

    root = paths.find_data_dir(data_dir)
    payload["data_dir"] = root
    if root is None:
        payload["message"] = "未找到 data/ 目录"
        _write_result(out_path, payload)
        return EXIT_USAGE

    if paths.is_frozen():
        ed = paths.exe_dir()
        payload["data_dir_inside_exe"] = paths.data_dir_is_inside(root, ed)
        if payload["data_dir_inside_exe"] is not True:
            payload["message"] = (
                "冻结态自检失败：数据目录 %s 未落在 exe 目录 %s 内——"
                "数据没有随包走，exe 回头读了开发机的仓库。" % (root, ed)
            )
            _write_result(out_path, payload)
            return EXIT_USAGE

    try:
        from .benchmark.runner import run_benchmarks
        from .engine.pipeline import build_context, gate_overview

        context = build_context(data_dir)
        payload["rulesets"] = gate_overview(context)
        payload["cutover"] = context.manifest.cutover
        payload["engine_ok"] = True
    except Exception as exc:  # noqa: BLE001 - 自检要如实记录任何失败
        payload["message"] = "规则库加载失败：%s" % exc
        _write_result(out_path, payload)
        return EXIT_USAGE

    try:
        code = run_benchmarks(only=None, data_dir=data_dir, as_json=False, quiet=True)
        payload["bench_ok"] = code == EXIT_OK
        payload["bench_exit_code"] = code
    except Exception as exc:  # noqa: BLE001
        payload["bench_ok"] = False
        payload["message"] = "基准运行失败：%s" % exc
        _write_result(out_path, payload)
        return EXIT_USAGE

    payload["ok"] = bool(payload["engine_ok"] and payload["bench_ok"])
    if payload["frozen"]:
        payload["ok"] = bool(payload["ok"] and payload["data_dir_inside_exe"])
    _write_result(out_path, payload)
    return EXIT_OK if payload["ok"] else EXIT_USAGE
