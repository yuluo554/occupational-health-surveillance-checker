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
    "compare",
    "build_report_model",
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
