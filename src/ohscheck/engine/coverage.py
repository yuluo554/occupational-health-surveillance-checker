"""覆盖度核查（FR-B2/B3/B5/B7）：应检 vs 实检 → 四态 + 缺项挂依据。

定级边界（plan/04 §3.2，写死避免漂移）：
    应检项全齐 + 周期合规                 → compliant
    缺 1 项以上必检项 / 周期超期           → partial
    必检项**一项未做**（expected ⊆ missing）→ non_compliant
    岗位危害因素不适用该人员               → not_applicable（**不计违规**，决策 D-22）
    危害因素不识别 / 缺必填字段            → 不产出 verdict，记 failed + 原因码
    别名归一不成立                         → 该单项降级 warning，不硬判缺失（决策 D-17）

unknown 是"非结论"：不降级为 compliant（决策 D-22）。
"""

from __future__ import annotations

from ..model import (
    NONCOMPLIANT_VERDICTS,
    VERDICT_COMPLIANT,
    VERDICT_NON_COMPLIANT,
    VERDICT_NOT_APPLICABLE,
    VERDICT_PARTIAL,
    VERDICT_UNKNOWN,
    CoverageResult,
)
from .matrix import STATE_INPUT_REQUIRED, STATE_NOT_APPLICABLE
from .period import (
    PERIOD_NOT_APPLICABLE,
    PERIOD_PENDING_INPUT,
    is_period_noncompliant,
    judge_period,
)


def normalize_items(items, known_codes=None, alias_map=None):
    """实检项目归一。

    归一顺序（决策 D-17，禁模糊匹配）：
        1. **精确命中规范代码**（known_codes 里已有）→ 原样保留。这是直接命中，
           与别名表是否启用无关。
        2. 显式别名表命中 → 映射到规范代码。
        3. 归一无结果 → 记入 unmapped（调用方降级 warning，不判缺失）。

    Args:
        items: 实检项目字符串列表。
        known_codes: 该时点的应检项目规范代码集合。
        alias_map: 显式别名表 {别名 → 规范代码}；None 或空 = 别名归一路径**整体禁用**
            （此时非精确命中的写法一律记 unmapped——**不猜**）。

    Returns:
        (normalized_set, unmapped_list)
    """
    alias_map = alias_map or {}
    known = set(known_codes or ())
    normalized = set()
    unmapped = []
    for raw in items:
        text = str(raw).strip()
        if text in known:
            normalized.add(text)  # 精确命中
            continue
        if text in alias_map:
            normalized.add(str(alias_map[text]))
            continue
        unmapped.append(text)
    return normalized, unmapped


def _classify(expected_set, missing_set, period_verdict):
    """按定级边界给出 verdict。"""
    period_bad = is_period_noncompliant(period_verdict)

    if not expected_set:
        # 该时点无必检项 → 无可比对；周期超期仍算违规
        return VERDICT_PARTIAL if period_bad else VERDICT_COMPLIANT

    if not missing_set:
        return VERDICT_PARTIAL if period_bad else VERDICT_COMPLIANT

    # 必检项一项未做（且 expected 非空）→ 不符合
    if expected_set.issubset(missing_set):
        return VERDICT_NON_COMPLIANT
    return VERDICT_PARTIAL


def check_record(record, plan_result, alias_map=None, last_exam_date=None):
    """核算单份监护档案（纯函数，单件与批量共用此分派点：决策 D-32）。

    Args:
        record: HealthRecord。
        plan_result: PlanResult（由 pipeline 预先按锚定版本推导）。
        alias_map: 显式别名表（None → 归一路径禁用，非精确命中记 unmapped warning）。
        last_exam_date: 同一人员上一次检查日期（周期判定基线；缺 → no_baseline，不报超期）。

    Returns:
        CoverageResult。
    """
    factor_plan = None
    for item in plan_result.factors:
        if item.factor_code == record.factor_code:
            factor_plan = item
            break

    if factor_plan is None:
        return CoverageResult(
            record_id=record.record_id,
            employee_id=record.employee_id,
            position_id=record.position_id,
            factor_code=record.factor_code,
            exam_type=record.exam_type,
            verdict=VERDICT_UNKNOWN,
            failed_reason="unknown_factor",
            failed_message="规则集中不存在危害因素 %r" % record.factor_code,
        )

    # 适用性：不适用 → not_applicable，不计违规（决策 D-22）
    if factor_plan.applicability.state == STATE_NOT_APPLICABLE:
        return CoverageResult(
            record_id=record.record_id,
            employee_id=record.employee_id,
            position_id=record.position_id,
            factor_code=record.factor_code,
            exam_type=record.exam_type,
            verdict=VERDICT_NOT_APPLICABLE,
            # 因素不适用 → 无周期义务；周期判定亦为"不适用"（而非留空，
            # 否则报告/统计会把"未判定"与"无义务"混同）。
            period_verdict=PERIOD_NOT_APPLICABLE,
            findings=[
                {
                    "kind": "not_applicable",
                    "message": factor_plan.applicability.reason,
                    "basis": factor_plan.applicability.basis,
                }
            ],
            trace=[
                {
                    "target": "%s/%s/applicability" % (record.record_id, record.factor_code),
                    "value": "not_applicable",
                    "basis": factor_plan.applicability.basis,
                }
            ],
        )

    # 适用性待输入 → unknown（不降级为 compliant，决策 D-22）
    if factor_plan.applicability.state == STATE_INPUT_REQUIRED:
        return CoverageResult(
            record_id=record.record_id,
            employee_id=record.employee_id,
            position_id=record.position_id,
            factor_code=record.factor_code,
            exam_type=record.exam_type,
            verdict=VERDICT_UNKNOWN,
            # 适用性未定 → 周期亦无法判定（不是"无义务"），如实记待输入。
            period_verdict=PERIOD_PENDING_INPUT,
            findings=[
                {
                    "kind": "input_required",
                    "message": factor_plan.applicability.reason,
                    "basis": factor_plan.applicability.basis,
                }
            ],
            failed_reason="missing_input",
            failed_message=factor_plan.applicability.reason,
        )

    exam = factor_plan.exams.get(record.exam_type)
    if exam is None:
        return CoverageResult(
            record_id=record.record_id,
            employee_id=record.employee_id,
            position_id=record.position_id,
            factor_code=record.factor_code,
            exam_type=record.exam_type,
            verdict=VERDICT_UNKNOWN,
            failed_reason="unknown_exam_type",
            failed_message="该因素的应检清单未包含时点 %r" % record.exam_type,
        )

    expected = set(exam.required_items)
    actual, unmapped = normalize_items(record.items, known_codes=expected, alias_map=alias_map)

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)

    # 周期判定
    period_verdict = None
    period_info = None
    if record.exam_type == "periodic":
        # 周期判定仅在"在岗期间"时点适用（其余时点无"距上次"语义）
        period_info = judge_period(factor_plan.period, last_exam_date, record.exam_date)
        period_verdict = period_info["verdict"]
    else:
        period_verdict = "not_applicable"

    verdict = _classify(expected, set(missing), period_verdict)

    findings = []
    trace = [
        {
            "target": "%s/%s/%s" % (record.record_id, record.factor_code, record.exam_type),
            "value": verdict,
            "basis": exam.basis,
        }
    ]
    for code in missing:
        item_basis = _item_basis(exam, code) or exam.basis
        finding = {
            "kind": "missing_item",
            "message": "缺必检项目 %s" % code,
            "item_code": code,
            "basis": item_basis,
        }
        source = _item_source(exam, code)
        if source:
            finding["source"] = source
        findings.append(finding)
        row = {
            "target": "%s/%s/%s/%s" % (record.record_id, record.factor_code, record.exam_type, code),
            "value": "missing",
            "basis": item_basis,
        }
        if source:
            row["source"] = source
        trace.append(row)
    for text in unmapped:
        # 别名归一不成立 → 降级 warning，不硬判缺失（决策 D-17）
        findings.append(
            {
                "kind": "warning",
                "message": "实检项目 %r 无法归一到规范项目代码（不判缺失，请人工确认）" % text,
                "basis": exam.basis,
                "item_code": text,
            }
        )
    if period_info and is_period_noncompliant(period_verdict):
        findings.append(
            {
                "kind": "period_overdue",
                "message": period_info.get("note") or "检查周期超期",
                "basis": factor_plan.basis,
            }
        )

    return CoverageResult(
        record_id=record.record_id,
        employee_id=record.employee_id,
        position_id=record.position_id,
        factor_code=record.factor_code,
        exam_type=record.exam_type,
        verdict=verdict,
        missing_items=missing,
        extra_items=extra,
        unmapped_items=unmapped,
        period_verdict=period_verdict,
        findings=findings,
        trace=trace,
    )


def _item_basis(exam, item_code):
    """取某必检项的条款依据（逐项优先，节级回落）。

    M1 数据入库后规则包 `required_items[].basis` 逐项可下钻（决策 D-16）；
    取不到逐项值时回落到节级 basis（合成夹具的逐项 basis 与节级同源，故等价）。
    """
    return exam.item_basis(item_code)


def _item_source(exam, item_code):
    """取某必检项的出处块（doc/clause/url/fetched）；无则空对象。"""
    return exam.item_source(item_code)


def is_noncompliant(coverage_result):
    """是否计入"检出不符合"（退出码 1 的判据）。"""
    return coverage_result.verdict in NONCOMPLIANT_VERDICTS


def verdict_reachability(ruleset):
    """四态在本规则包上的**可达性**（D-59：不可达必须显式声明，不假装覆盖）。

    判据由**规则包数据结构**实算（非猜测）：
      * `not_applicable`：仅当存在 `eligibility.kind == "threshold"` 的因素时可达
        （标准对所列危害因素"接触即纳入"→ 全 `always` 时不可达）；
      * `unknown`（适用性待输入）：存在 `kind == "input_required"` 的适用性时可达；
      * `compliant` / `partial` / `non_compliant`：由必检项与实检项比对决定，恒可达。

    Args:
        ruleset: Ruleset（或 EffectiveRuleset.ruleset）。

    Returns:
        list[dict]: [{state, reachable, reason}]，按状态名排序。
    """
    kinds = set()
    for factor in ruleset.factors:
        kinds.add((factor.get("eligibility") or {}).get("kind"))
    threshold = "threshold" in kinds
    input_req = "input_required" in kinds
    rows = [
        {
            "state": "not_applicable",
            "reachable": threshold,
            "reason": (
                "规则包含接触水平阈值型适用性（kind=threshold）"
                if threshold
                else "标准对所列危害因素「接触即纳入」，全为 kind=always；"
                "逐因素不设接触水平阈值 → 本规则包不可达"
            ),
        },
        {
            "state": "unknown",
            "reachable": input_req,
            "reason": (
                "存在适用性待输入（kind=input_required）"
                if input_req
                else "无适用性待输入条目"
            ),
        },
        {
            "state": "compliant",
            "reachable": True,
            "reason": "必检项齐备且周期合规时可达",
        },
        {
            "state": "partial",
            "reachable": True,
            "reason": "存在缺项或周期超期时可达",
        },
        {
            "state": "non_compliant",
            "reachable": True,
            "reason": "必检项一项未做时可达",
        },
    ]
    return sorted(rows, key=lambda r: r["state"])
