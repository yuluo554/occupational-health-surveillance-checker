"""编排层：CLI 与 GUI 共用的**唯一**编排事实源（决策 D-31 / D-33 / FR-G3）。

表现层只准经本模块的公开函数取数，不得自行拼装判定或读规则包。
IO（读盘/规则加载/门控）集中在此；判定层保持纯函数。
"""

from __future__ import annotations

from ..errors import MissingInputError
from ..model import HealthRecord, PositionProfile
from ..rules import load_manifest, load_ruleset
from ..rules.gate import effective_ruleset
from ..rules.version import resolve_ruleset_id

# 编排层公开函数组（表现层唯一入口）
__all__ = [
    "build_context",
    "build_position",
    "build_record",
    "resolve_ruleset_for",
    "compute_plan",
    "compute_coverage",
    "run_scan",
    "scan_with_reconcile",
    "compare",
    "compare_rounds_model",
    "build_report_model",
    "generate_report",
    "report_from_inputs",
    "selfcheck_payload",
    "parameter_overview",
    "gate_overview",
]


class Context:
    """一次运行的上下文（manifest + 按需载入的规则集缓存）。"""

    __slots__ = ("data_dir", "manifest", "_rulesets")

    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        self.manifest = load_manifest(data_dir)
        self._rulesets = {}

    def ruleset(self, ruleset_id):
        if ruleset_id not in self._rulesets:
            self._rulesets[ruleset_id] = load_ruleset(
                ruleset_id, self.data_dir, self.manifest
            )
        return self._rulesets[ruleset_id]

    def all_rulesets(self):
        return {rid: self.ruleset(rid) for rid in self.manifest.ruleset_ids()}


def build_context(data_dir=None):
    """装配运行上下文（唯一 IO 入口）。"""
    return Context(data_dir)


def build_position(obj):
    """从裸字典建岗位画像（输入解释全项目只剩这一处实现）。"""
    return PositionProfile.from_dict(obj)


def build_record(obj):
    """从裸字典建监护档案。"""
    if isinstance(obj, dict) and "record_id" not in obj and isinstance(obj.get("record"), dict):
        obj = obj["record"]
    return HealthRecord.from_dict(obj)


def resolve_ruleset_for(exam_date, context):
    """按体检日期锚定规则版本并返回 Ruleset（决策 D-10/D-11）。"""
    ruleset_id = resolve_ruleset_id(exam_date, context.manifest)
    return context.ruleset(ruleset_id)


def _blocking_inputs(items):
    """只取**阻塞性**待输入项（周期级待输入不阻断，见 rules/gate.py 的阻塞性分级）。

    M1 实测发现 A：22 个主要因素的周期标准按作业分级分档、规则包不承载单值，
    但其应检项已可完全推导 → 不应阻断 plan/check。真正的"不给出就无法判定"
    （适用性 / 项目级）才拦。
    """
    return [it for it in items if it.get("blocking", True)]


def compute_plan(profile, context, scope="plan"):
    """岗位应检清单推导（含门控；待输入则抛 MissingInputError）。

    Raises:
        GateBlocked: 引用到的条目里有 pending。
        MissingInputError: 适用性/项目级需外部输入（绝不静默取默认值，决策 D-13）。
    """
    from ..engine.matrix import compute_plan as _compute

    ruleset = resolve_ruleset_for(profile.exam_date, context)
    eff = effective_ruleset(ruleset, scope, required_factor_ids=profile.factor_codes)
    blocking = _blocking_inputs(eff.missing_inputs)
    if blocking:
        raise MissingInputError(blocking)
    result = _compute(profile, eff)
    result_blocking = _blocking_inputs(result.missing_inputs)
    if result_blocking:
        raise MissingInputError(result_blocking)
    return result


def _plan_for_record(record, context, scope="check"):
    """给一份档案推导其适用的应检清单（单件与批量共用）。

    Returns:
        (PlanResult, last_exam_date) —— last_exam_date 取自档案自身的
        `last_exam_date` 字段（周期判定基线）；缺则 None → no_baseline。
    """
    from ..engine.matrix import compute_plan as _compute

    ruleset = resolve_ruleset_for(record.exam_date, context)
    eff = effective_ruleset(ruleset, scope, required_factor_ids=[record.factor_code])
    blocking = _blocking_inputs(eff.missing_inputs)
    if blocking:
        raise MissingInputError(blocking)

    # 用档案自身的岗位画像（单因素）推导应检清单
    profile = PositionProfile(
        position_id=record.position_id or record.record_id,
        exam_date=record.exam_date,
        factors=[_factor_ref_stub(record.factor_code)],
    )
    plan_result = _compute(profile, eff)
    plan_blocking = _blocking_inputs(plan_result.missing_inputs)
    if plan_blocking:
        raise MissingInputError(plan_blocking)
    return plan_result, record.last_exam_date


def _factor_ref_stub(factor_code):
    from ..model import FactorRef

    return FactorRef(factor_code)


def compute_coverage(record, context):
    """单件覆盖度核查（与批量共用同一分派点，决策 D-32）。"""
    from ..engine.coverage import check_record

    plan_result, last_exam_date = _plan_for_record(record, context)
    alias_map = _alias_map(context, plan_result.ruleset_id)
    return check_record(
        record, plan_result, alias_map=alias_map, last_exam_date=last_exam_date
    )


def run_scan(directory, context, max_bytes=None):
    """批量扫描（含失败隔离，决策 D-21）。"""
    from ..engine.scan import DEFAULT_MAX_BYTES, scan_directory

    def provider(factor_code, exam_date, record):
        return _plan_for_record(record, context)

    kwargs = {}
    if max_bytes is not None:
        kwargs["max_bytes"] = max_bytes
    return scan_directory(
        directory,
        provider,
        alias_map=_alias_map(context, None),
        max_bytes=kwargs.get("max_bytes", DEFAULT_MAX_BYTES),
    )


def compare_rounds_model(current_scan, baseline_scan):
    """跨轮对账（M3-3 / FR-D3）：对账口径单一实现源（engine/reconcile.py）。"""
    from ..engine.reconcile import compare_rounds

    return compare_rounds(current_scan, baseline_scan)


def scan_with_reconcile(directory, context, baseline_directory=None):
    """批量扫描 + 可选跨轮对账（M5-1 上收：CLI `scan`/`report` 与 GUI 共用）。

    Args:
        directory: 当前轮档案目录。
        baseline_directory: 上一轮档案目录（None → 不对账）。

    Returns:
        (ScanResult, baseline_result_or_None, reconcile_result_or_None)
    """
    result = run_scan(directory, context)
    baseline_result = None
    reconcile = None
    if baseline_directory:
        baseline_result = run_scan(baseline_directory, context)
        reconcile = compare_rounds_model(result, baseline_result)
    return result, baseline_result, reconcile


def _alias_map(context, ruleset_id):
    """取显式别名表；pending 或未定义 → 返回 None（归一路径整体禁用，决策 D-17）。"""
    ids = [ruleset_id] if ruleset_id else context.manifest.ruleset_ids()
    merged = {}
    any_verified = False
    for rid in ids:
        ruleset = context.ruleset(rid)
        block = ruleset.obj.get("alias_map")
        if not isinstance(block, dict):
            continue
        if block.get("status") != "verified":
            # pending 时归一路径整体禁用——不猜
            continue
        any_verified = True
        for alias, code in (block.get("map") or {}).items():
            merged[alias] = code
    return merged if any_verified else None


def compare(ruleset_id_a, ruleset_id_b, context):
    """版本差异对照（FR-C3）。"""
    from ..engine.compare import compare_rulesets

    eff_a = effective_ruleset(context.ruleset(ruleset_id_a), "compare")
    eff_b = effective_ruleset(context.ruleset(ruleset_id_b), "compare")
    return compare_rulesets(eff_a, eff_b)


def build_report_model(*, plan_result=None, coverage_results=None, scan_result=None,
                       reconcile_result=None, context=None, ruleset_id=None,
                       generated_at=None):
    """构造报告模型（供 report/ 单一渲染源消费）。"""
    from ..report.sections import build_model

    return build_model(
        plan_result=plan_result,
        coverage_results=coverage_results,
        scan_result=scan_result,
        reconcile_result=reconcile_result,
        context=context,
        ruleset_id=ruleset_id,
        generated_at=generated_at,
    )


def parameter_overview(context):
    """规则包坐标与出处总览（报告 §9 参数来源块）。"""
    out = []
    for rid in context.manifest.ruleset_ids():
        ruleset = context.ruleset(rid)
        basis = ruleset.basis
        entry = context.manifest.entry(rid) or {}
        out.append(
            {
                "ruleset_id": rid,
                "doc_code": basis.get("doc_code", ""),
                "doc_title": basis.get("doc_title", ""),
                "issuer": basis.get("issuer", ""),
                "doc_number": basis.get("doc_number", ""),
                "published": basis.get("published", ""),
                "effective_from": basis.get("effective_from", ""),
                "replaces": basis.get("replaces", ""),
                "url": basis.get("url", ""),
                "fetched": basis.get("fetched", ""),
                "sha256": entry.get("sha256", ""),
            }
        )
    return out


def gate_overview(context, scope="plan"):
    """各规则集的核对状态总览（selfcheck 与报告用）。"""
    from ..rules.gate import pending_report

    rows = []
    for rid in context.manifest.ruleset_ids():
        ruleset = context.ruleset(rid)
        pending, inputs = pending_report(ruleset, scope)
        rows.append(
            {
                "ruleset_id": rid,
                "status_counts": ruleset.status_counts(),
                "pending_count": len(pending),
                "input_required_count": len(inputs),
                "factor_count": len(ruleset.factors),
            }
        )
    return rows


def policy_thresholds(context):
    """基准验收门槛（随 manifest 下发，决策 D-24）。"""
    return context.manifest.thresholds


def generate_report(*, out_dir, context, generated_at, plan_result=None,
                    coverage_results=None, scan_result=None, reconcile_result=None,
                    input_paths=None):
    """报告装配 + 导出全链路（M5-1 上收：CLI `report` 与 GUI 共用）。

    报告模型构造、规则集 sha256 提取、溯源硬断言、三件套落盘都在这里；
    表现层只提供输入与目标目录。

    Returns:
        export_report 的路径 dict（markdown/xlsx/evidence/sha256）。
    """
    from ..engine.export import export_report

    ruleset_id = plan_result.ruleset_id if plan_result is not None else ""
    model = build_report_model(
        plan_result=plan_result,
        coverage_results=coverage_results,
        scan_result=scan_result,
        reconcile_result=reconcile_result,
        context=context,
        ruleset_id=ruleset_id,
        generated_at=generated_at,
    )
    ruleset_sha = ""
    if ruleset_id:
        entry = context.manifest.entry(ruleset_id) or {}
        ruleset_sha = entry.get("sha256", "")
    return export_report(
        model, out_dir, ruleset_id=ruleset_id, ruleset_sha256=ruleset_sha,
        input_paths=input_paths,
    )


def report_from_inputs(*, out_dir, context, generated_at, position_path=None,
                       record_path=None, directory=None, baseline=None):
    """从输入路径到报告落盘的整段编排（M5-1 上收：CLI `report` 与 GUI 共用）。

    与 CLI `report` 子命令同语义：三种来源可任意组合（plan/record/directory，
    baseline 需先给 directory）；输入路径逐个挂进证据链。

    Returns:
        export_report 的路径 dict。
    """
    from ..loaders import load_path

    plan_result = coverage_results = scan_result = reconcile_result = None
    input_paths = []
    if directory:
        scan_result, _baseline_result, reconcile_result = scan_with_reconcile(
            directory, context, baseline
        )
        input_paths.append(directory)
        if baseline:
            input_paths.append(baseline)
    if record_path:
        record = build_record(load_path(record_path))
        coverage_results = [compute_coverage(record, context)]
        input_paths.append(record_path)
    if position_path:
        profile = build_position(load_path(position_path))
        plan_result = compute_plan(profile, context)
        input_paths.append(position_path)
    return generate_report(
        out_dir=out_dir,
        context=context,
        generated_at=generated_at,
        plan_result=plan_result,
        coverage_results=coverage_results,
        scan_result=scan_result,
        reconcile_result=reconcile_result,
        input_paths=input_paths,
    )


def selfcheck_payload(data_dir=None):
    """自检负载装配（M5-1 上收：CLI `selfcheck` 与 GUI 自检页共用）。

    数据目录定位、规则库加载、门控计数、参数来源都在这里；
    返回 (payload_dict, exit_code)，表现层只负责渲染。

    定位失败时 exit_code 为 2（EXIT_USAGE）且 status=FAIL。
    """
    from .. import paths
    from ..errors import EXIT_OK, EXIT_USAGE

    info = paths.describe_search()
    payload = {
        "version": _version(),
        "python": _python_version(),
        "frozen": info["frozen"],
        "data_dir": info["resolved"],
        "candidates": info["candidates"],
    }
    if info["resolved"] is None or not _isdir(info["resolved"]):
        payload["status"] = "FAIL"
        payload["message"] = "未找到 data/ 目录：%s" % (info["resolved"] or "（无候选命中）")
        return payload, EXIT_USAGE

    context = build_context(data_dir)
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
            "引用到这些条目的 plan/check 会被门控拦截（退出码 2）；"
            "compare/bench 走 minimal 深度，不受项目明细 pending 影响。" % total_pending
        )
    return payload, EXIT_OK


def _version():
    from .. import __version__

    return __version__


def _python_version():
    import sys

    return sys.version.split()[0]


def _isdir(path):
    import os

    return os.path.isdir(path) if path else False
