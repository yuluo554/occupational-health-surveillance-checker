"""命令行入口（FR-G1）。

退出码契约（plan/03 §七，锁进测试）：
    0 成功且无不符合项 / 基准全达标
    1 成功但检出不符合 / 基准未达标
    2 用法、输入或坐标错误（含门控拦截与 input_required 未提供）
    3 可选依赖缺失

编码守卫（决策 D-39）：入口一律 _ensure_utf8_stdio()，
按 stream.encoding 探针决定是否 reconfigure——中文控制台保持不动，
cp1252 管道不崩（对应 CI 上的编码差异型失败）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .errors import (
    EXIT_MISSING_DEPENDENCY,
    EXIT_NONCOMPLIANT,
    EXIT_OK,
    EXIT_USAGE,
    OhsCheckError,
    UsageError,
)


def _ensure_utf8_stdio():
    """按 stream.encoding 探针决定是否 reconfigure（决策 D-39）。

    探针式而非无条件：中文控制台（cp936）保持不动，避免破坏本机显示；
    编码无法表示非 ASCII 时（如 cp1252 管道）才切到 UTF-8 且 errors=replace。
    """
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


def _dump(obj, as_json):
    """输出：--json 走确定性 JSON，否则人读。"""
    if as_json:
        from .loaders import dumps_stable

        sys.stdout.write(dumps_stable(obj))
        return
    _print_human(obj)


def _print_human(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                sys.stdout.write("%s:\n" % key)
                _print_human(value)
            else:
                sys.stdout.write("  %s: %s\n" % (key, value))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                sys.stdout.write("- " + json.dumps(item, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write("- %s\n" % item)
    else:
        sys.stdout.write("%s\n" % obj)


# ---------------- 子命令 ----------------


def cmd_version(args):
    _dump({"name": "ohscheck", "version": __version__, "python": sys.version.split()[0]},
          args.json)
    return EXIT_OK


def cmd_selfcheck(args):
    """数据目录定位 + 规则库加载 + status 门控计数。"""
    from . import paths
    from .engine.pipeline import build_context, gate_overview, parameter_overview

    info = paths.describe_search()
    payload = {
        "version": __version__,
        "python": sys.version.split()[0],
        "frozen": info["frozen"],
        "data_dir": info["resolved"],
        "candidates": info["candidates"],
    }
    if info["resolved"] is None or not os.path.isdir(info["resolved"]):
        payload["status"] = "FAIL"
        payload["message"] = "未找到 data/ 目录：%s" % (info["resolved"] or "（无候选命中）")
        _dump(payload, args.json)
        return EXIT_USAGE

    context = build_context(args.data_dir)
    payload["cutover"] = context.manifest.cutover
    payload["rulesets"] = gate_overview(context)
    payload["parameter_sources"] = [
        {k: v for k, v in row.items() if k != "sha256"} for row in parameter_overview(context)
    ]
    total_pending = sum(row["pending_count"] for row in payload["rulesets"])
    payload["pending_total"] = total_pending
    payload["status"] = "OK"
    if total_pending:
        payload["message"] = (
            "规则包有 %d 处条目尚未核对（status=pending）：未核对不得进入核查路径。"
            "M0 期初态即全部 pending。" % total_pending
        )
    _dump(payload, args.json)
    return EXIT_OK


def cmd_plan(args):
    """应检项目与周期推导。"""
    from .engine.pipeline import build_context, build_position, compute_plan
    from .loaders import load_path

    context = build_context(args.data_dir)
    profile = build_position(load_path(args.path))
    result = compute_plan(profile, context)
    _dump(result.as_dict(), args.json)
    return EXIT_OK


def cmd_check(args):
    """单件覆盖度核查。"""
    from .engine.pipeline import build_context, build_record, compute_coverage
    from .loaders import load_path
    from .model import NONCOMPLIANT_VERDICTS

    context = build_context(args.data_dir)
    record = build_record(load_path(args.path))
    result = compute_coverage(record, context)
    payload = result.as_dict()
    _dump(payload, args.json)
    return EXIT_NONCOMPLIANT if result.verdict in NONCOMPLIANT_VERDICTS else EXIT_OK


def cmd_scan(args):
    """批量扫描 + 报告导出。"""
    from .engine.pipeline import build_context, run_scan
    from .model import NONCOMPLIANT_VERDICTS

    context = build_context(args.data_dir)
    result = run_scan(args.directory, context)
    payload = result.as_dict()
    if args.out:
        from .engine.export import export_report
        from .engine.pipeline import build_report_model

        model = build_report_model(
            scan_result=result, context=context, generated_at=args.generated_at
        )
        paths_out = export_report(model, args.out)
        payload["report"] = paths_out
    _dump(payload, args.json)
    for rec in result.items:
        if rec.verdict in NONCOMPLIANT_VERDICTS:
            return EXIT_NONCOMPLIANT
    return EXIT_OK


def cmd_compare(args):
    """双版本差异对照。"""
    from .engine.pipeline import build_context, compare

    context = build_context(args.data_dir)
    ids = context.manifest.ruleset_ids()
    id_a = args.old or (ids[0] if ids else "")
    id_b = args.new or (ids[-1] if ids else "")
    report = compare(id_a, id_b, context)
    _dump(report.as_dict(), args.json)
    return EXIT_OK


def cmd_report(args):
    """导出报告（plan / check / scan 三种来源）。"""
    from .engine.export import export_report
    from .engine.pipeline import (
        build_context,
        build_position,
        build_record,
        build_report_model,
        compute_coverage,
        compute_plan,
        run_scan,
    )
    from .loaders import load_path

    context = build_context(args.data_dir)
    plan_result = coverage_results = scan_result = None
    input_paths = []

    if args.directory:
        scan_result = run_scan(args.directory, context)
        input_paths.append(args.directory)
    if getattr(args, "record", None):
        record = build_record(load_path(args.record))
        coverage_results = [compute_coverage(record, context)]
        input_paths.append(args.record)
    if args.position:
        profile = build_position(load_path(args.position))
        plan_result = compute_plan(profile, context)
        input_paths.append(args.position)

    ruleset_id = plan_result.ruleset_id if plan_result is not None else ""
    model = build_report_model(
        plan_result=plan_result,
        coverage_results=coverage_results,
        scan_result=scan_result,
        context=context,
        ruleset_id=ruleset_id,
        generated_at=args.generated_at,
    )
    ruleset_sha = ""
    if ruleset_id:
        entry = context.manifest.entry(ruleset_id) or {}
        ruleset_sha = entry.get("sha256", "")
    paths_out = export_report(
        model, args.out, ruleset_id=ruleset_id, ruleset_sha256=ruleset_sha,
        input_paths=input_paths,
    )
    _dump(paths_out, args.json)
    return EXIT_OK


def cmd_bench(args):
    """内置评测基准（门槛随 manifest 下发）。"""
    from .benchmark.runner import run_benchmarks

    return run_benchmarks(
        only=args.only,
        data_dir=args.data_dir,
        as_json=args.json,
    )


def cmd_gui(args):
    """启动桌面界面（可选 extra；缺依赖 → 退出码 3）。

    惰性导入的 try **包住从 import 到调用完成的整段**（决策 D-38）：
    分层守门要求重件只在函数体内 import，故此处的边界是 build_app()/main()，
    不是 import 语句本身。
    """
    try:
        from .gui.main_window import main as gui_main

        return gui_main(args.data_dir)
    except ImportError as exc:
        sys.stderr.write(
            "桌面界面需要 PySide6（可选依赖）。源码态安装：pip install -e \".[gui]\"\n"
            "缺失详情：%s\n" % exc
        )
        return EXIT_MISSING_DEPENDENCY


def cmd_selftest(args):
    """冻结态自检：数据定位 + 全链路 + 基准，结论写文件回传（FR-G5）。"""
    from ._selftest import run_selftest

    return run_selftest(args.out, args.data_dir)


# ---------------- 参数解析 ----------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ohscheck",
        description="职业健康监护合规核查工作台（GBZ 188 双版本规则集）",
    )
    parser.add_argument("--version", action="version", version="ohscheck %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=None, help="data/ 目录（默认自动定位）")
    common.add_argument("--json", action="store_true", help="以 JSON 输出")

    p = sub.add_parser("version", help="版本信息", parents=[common])
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("selfcheck", help="数据目录 + 规则库 + 门控计数", parents=[common])
    p.set_defaults(func=cmd_selfcheck)

    p = sub.add_parser("plan", help="岗位应检项目与周期推导", parents=[common])
    p.add_argument("path", help="岗位画像 JSON 路径")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("check", help="单件监护档案覆盖度核查", parents=[common])
    p.add_argument("path", help="监护档案 JSON 路径")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("scan", help="批量扫描监护档案", parents=[common])
    p.add_argument("directory", help="档案目录")
    p.add_argument("--out", default=None, help="报告输出目录")
    p.add_argument("--generated-at", default=None, help="报告生成时间（注入以保持可复现）")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("compare", help="双版本差异对照", parents=[common])
    p.add_argument("--old", default=None, help="旧版 ruleset_id")
    p.add_argument("--new", default=None, help="新版 ruleset_id")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("report", help="导出报告（Markdown + XLSX + 证据链）", parents=[common])
    p.add_argument("out", help="报告输出目录")
    p.add_argument("--position", default=None, help="岗位画像 JSON（可选）")
    p.add_argument("--record", default=None, help="单件档案 JSON（可选）")
    p.add_argument("--directory", default=None, help="档案目录（可选）")
    p.add_argument("--generated-at", default=None, help="报告生成时间（注入以保持可复现）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("bench", help="内置评测基准", parents=[common])
    p.add_argument("--only", default=None, help="只跑指定套件")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("gui", help="启动桌面界面（需 [gui] extra）", parents=[common])
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("selftest", help="冻结态自检（结论写文件回传）", parents=[common])
    p.add_argument("out", help="自检结论输出文件")
    p.set_defaults(func=cmd_selftest)

    return parser


def main(argv=None):
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.func(args)
    except OhsCheckError as exc:
        sys.stderr.write("错误：%s\n" % exc.message)
        if getattr(exc, "reason", None):
            sys.stderr.write("原因码：%s\n" % exc.reason)
        return exc.exit_code
    except UsageError as exc:  # pragma: no cover - 基类已覆盖
        sys.stderr.write("用法错误：%s\n" % exc)
        return EXIT_USAGE
    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("已中断\n")
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
