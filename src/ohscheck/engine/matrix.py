"""监护矩阵推导（FR-A2/A3/A4/A5）。

应检项集口径（决策 D-16，动了会打挂基准）：
    expected = required_items（**只算必检项**）
    supplementary_items / optional_items 不进判定（缺失不报）
理由：补充项标准表述含"必要时"，属条件性项目；纳入判定会把
"医生按临床判断未做"误判成缺项（假阳性）。

推论的诚实留档：本工具**不做**"该做补充检查没做"的判定。README 限制节必须明示。
"""

from __future__ import annotations

from ..model import EXAM_TYPES, Applicability, ExamPlan, FactorPlan, PlanResult

STATE_APPLICABLE = "applicable"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_INPUT_REQUIRED = "input_required"

_COMPARATORS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _basis_text(basis, factor):
    """构造条款依据文本，逐项挂节号（FR-A4）。"""
    doc = (basis or {}).get("doc_code") or factor.get("basis") or ""
    clause = factor.get("factor_id") or ""
    if doc and clause:
        return "%s 第 %s 节" % (doc, clause)
    return clause or doc


def _judge_applicability(factor, factor_ref):
    """适用性三态判定（FR-B7：不适用 ≠ 违规）。"""
    elig = factor["eligibility"]
    kind = elig.get("kind")
    basis = _basis_text(None, factor)

    if kind == "pending":
        # 门控应已拦截；兜底不判适用
        return Applicability(STATE_INPUT_REQUIRED, "适用性条目尚未核对", basis)

    if kind == "input_required":
        return Applicability(
            STATE_INPUT_REQUIRED, elig.get("basis") or "适用性需按具体情况确定", basis
        )

    if kind == "always":
        return Applicability(STATE_APPLICABLE, "该危害因素一律纳入监护", basis)

    if kind == "threshold":
        comparator = _COMPARATORS.get(elig.get("comparator"))
        if comparator is None:
            raise ValueError("未知比较符 %r" % (elig.get("comparator"),))
        threshold = elig.get("threshold")
        if threshold is None:
            # schema 保证 verified 才有值；此处兜底不猜
            return Applicability(STATE_INPUT_REQUIRED, "适用性阈值尚未核对", basis)
        if factor_ref.exposure_value is None:
            # 未提供接触水平 → 显式索取，绝不静默取默认值（决策 D-13）
            return Applicability(
                STATE_INPUT_REQUIRED,
                "需提供接触浓度/强度（%s %s）方可判定适用性"
                % (elig.get("comparator"), elig.get("unit")),
                basis,
            )
        ok = comparator(factor_ref.exposure_value, threshold)
        return Applicability(
            STATE_APPLICABLE if ok else STATE_NOT_APPLICABLE,
            "接触水平 %s %s %s 阈值 %s"
            % (factor_ref.exposure_value, elig.get("unit"), elig.get("comparator"), threshold),
            basis,
        )

    raise ValueError("未知适用性类型 %r" % (kind,))


def _required_item_codes(block):
    """取必检项代码（只含已核对的项；pending 项由门控拦下，不在此静默跳过）。"""
    out = []
    for item in block.get("required_items") or []:
        code = item.get("item_code")
        if code:
            out.append(code)
    return out


def _build_exams(factor, basis_text):
    """构造四时点的应检清单。"""
    exams = {}
    for key in EXAM_TYPES:
        block = factor["examinations"][key]
        exams[key] = ExamPlan(
            exam_type=key,
            required_items=_required_item_codes(block),
            supplementary_items=[i.get("item_code") for i in block.get("supplementary_items") or []],
            optional_items=[i.get("item_code") for i in block.get("optional_items") or []],
            basis=basis_text,
        )
    return exams


def plan_for_factor(factor, factor_ref, ruleset_id):
    """单因素应检推导（纯函数）。"""
    basis_text = _basis_text(factor.get("basis"), factor)
    applicability = _judge_applicability(factor, factor_ref)

    exams = {}
    if applicability.state == STATE_APPLICABLE:
        exams = _build_exams(factor, basis_text)

    return FactorPlan(
        factor_code=factor["factor_code"],
        factor_name=factor["factor_name"],
        applicability=applicability,
        exams=exams,
        period=dict(factor["period"]),
        basis=basis_text,
    )


def _trace_rows(position_id, plan_result_factors):
    """溯源行：每条产出挂条款依据（FR-A4）。"""
    rows = []
    for factor_plan in plan_result_factors:
        if factor_plan.applicability.state != STATE_APPLICABLE:
            rows.append(
                {
                    "target": "%s/%s/applicability" % (position_id, factor_plan.factor_code),
                    "value": factor_plan.applicability.state,
                    "basis": factor_plan.applicability.basis,
                }
            )
            continue
        rows.append(
            {
                "target": "%s/%s/period" % (position_id, factor_plan.factor_code),
                "value": factor_plan.period.get("kind", ""),
                "basis": factor_plan.basis,
            }
        )
        for exam_type in EXAM_TYPES:
            exam = factor_plan.exams.get(exam_type)
            if exam is None:
                continue
            for code in exam.required_items:
                rows.append(
                    {
                        "target": "%s/%s/%s/%s"
                        % (position_id, factor_plan.factor_code, exam_type, code),
                        "value": "required",
                        "basis": exam.basis,
                    }
                )
    return rows


def compute_plan(profile, eff_ruleset):
    """矩阵推导主入口（纯函数）。

    Args:
        profile: PositionProfile。
        eff_ruleset: EffectiveRuleset（已过门控）。

    Returns:
        PlanResult（含 missing_inputs 与 trace）。
    """
    ruleset = eff_ruleset.ruleset
    factors = []
    missing_inputs = []

    for ref in profile.factors:
        factor = ruleset.factor(ref.factor_code)
        if factor is None:
            # 门控已校验 codes 存在；此处兜底
            raise ValueError("规则集中不存在危害因素 %r" % ref.factor_code)
        fp = plan_for_factor(factor, ref, ruleset.ruleset_id)
        factors.append(fp)
        if fp.applicability.state == STATE_INPUT_REQUIRED:
            missing_inputs.append(
                {
                    "target": "%s/%s/applicability" % (profile.position_id, ref.factor_code),
                    "basis": fp.applicability.reason,
                    "factor_code": ref.factor_code,
                }
            )

    notes = []
    if missing_inputs:
        notes.append(
            "有 %d 项适用性待外部输入，未满足前不产出该因素的应检清单" % len(missing_inputs)
        )

    return PlanResult(
        ruleset_id=ruleset.ruleset_id,
        position_id=profile.position_id,
        factors=factors,
        missing_inputs=missing_inputs,
        trace=_trace_rows(profile.position_id, factors),
        notes=notes,
    )


def expected_items(plan_result, factor_code, exam_type):
    """从推导结果取某因素某时点的应检项集合（判定用，决策 D-16）。"""
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code != factor_code:
            continue
        exam = factor_plan.exams.get(exam_type)
        if exam is None:
            return []
        return list(exam.required_items)
    return []


def applicability_of(plan_result, factor_code):
    """取某因素的适用性判定；找不到返回 None。"""
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code == factor_code:
            return factor_plan.applicability
    return None


def period_rule_of(plan_result, factor_code):
    """取某因素的周期规则；找不到返回 None。"""
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code == factor_code:
            return factor_plan.period
    return None
