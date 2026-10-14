"""溯源硬断言（FR-A4 / plan/04 §2.3）。

纪律：**不满足即拒导**——绝不留"半溯源报告"。判据两条（写死，避免漂移）：
  ① 行数对账：`len(trace) >= len(明细行) + len(因素行)`；
     明细行 = 已推导的必检项总数；因素行 = 因素级产出行（适用性/周期）数。
  ② 每条 trace 的 `basis` 非空。

为什么是"≥"而非"=="：trace 允许**多**出辅助行（如不适用因素的适用性行），
但**不得少**于"每条应检项 + 每个因素各一行"这个下界。少于下界即意味着
某条产出没有溯源——这正是要拒导的情形。

拒导是**结构性**的：调用方（report/export）拿到的不是"带警告的报告"，
而是本模块抛出的 `TraceAssertionError`（退出码 2，宁报错不产半成品）。
"""

from __future__ import annotations

from ..errors import OhsCheckError

REASON_TRACE_INCOMPLETE = "trace_incomplete"


class TraceAssertionError(OhsCheckError):
    """溯源硬断言不满足 → 拒导（不产出半溯源报告）。"""

    reason = REASON_TRACE_INCOMPLETE
    exit_code = 2

    def __init__(self, message, violations=None):
        super().__init__(message)
        self.violations = list(violations or [])


def expected_trace_lower_bound(plan_result):
    """因素行 + 明细行的下界（plan/04 §2.3 的 `len(明细行) + len(因素行)`）。

      * 因素行：每个因素 1 行（适用性结论行；适用时另计周期行，故 ≥ 1）；
      * 明细行：每个适用因素的四时点必检项总数。

    返回 (lower_bound, factors, detail_rows)。
    """
    factors = len(plan_result.factors)
    detail_rows = 0
    for factor_plan in plan_result.factors:
        for exam in factor_plan.exams.values():
            detail_rows += len(exam.required_items)
    return factors + detail_rows, factors, detail_rows


def assert_plan_trace(plan_result):
    """断言推导结果的溯源完整性；不满足抛 TraceAssertionError。

    Args:
        plan_result: PlanResult。

    Returns:
        dict: {lower_bound, factors, detail_rows, trace_rows}

    Raises:
        TraceAssertionError: 行数低于下界，或存在 basis 为空的 trace 行。
    """
    lower_bound, factors, detail_rows = expected_trace_lower_bound(plan_result)
    rows = list(plan_result.trace)
    violations = []

    if len(rows) < lower_bound:
        violations.append(
            "溯源行数不足：实际 %d < 下界 %d（因素行 %d + 明细行 %d）"
            % (len(rows), lower_bound, factors, detail_rows)
        )
    empty_basis = [
        row.get("target", "") for row in rows if not str(row.get("basis") or "").strip()
    ]
    if empty_basis:
        violations.append(
            "有 %d 条溯源行 basis 为空：%s" % (len(empty_basis), ", ".join(empty_basis[:8]))
        )

    if violations:
        raise TraceAssertionError(
            "溯源硬断言不满足，拒绝导出（不留半溯源报告）：%s" % "；".join(violations),
            violations=violations,
        )
    return {
        "lower_bound": lower_bound,
        "factors": factors,
        "detail_rows": detail_rows,
        "trace_rows": len(rows),
    }


def assert_coverage_trace(coverage_result):
    """断言单件核查结果的溯源完整性。

    判据：结果**产出结论**时（非 failed/unknown），至少要有 1 条 basis 非空的 trace 行
    （结论行），且缺项行逐项挂 basis。failed/unknown 不产出结论 → 不适用本断言
    （它们的"未判定"由原因码承载，不冒充溯源）。
    """
    if coverage_result.verdict in ("failed", "unknown"):
        return {"applicable": False, "trace_rows": len(coverage_result.trace)}
    rows = list(coverage_result.trace)
    violations = []
    if not rows:
        violations.append("产出结论但无溯源行（%s）" % coverage_result.record_id)
    empty_basis = [
        row.get("target", "") for row in rows if not str(row.get("basis") or "").strip()
    ]
    if empty_basis:
        violations.append(
            "有 %d 条溯源行 basis 为空：%s" % (len(empty_basis), ", ".join(empty_basis[:8]))
        )
    if violations:
        raise TraceAssertionError(
            "溯源硬断言不满足，拒绝导出（不留半溯源报告）：%s" % "；".join(violations),
            violations=violations,
        )
    return {"applicable": True, "trace_rows": len(rows)}


def assert_report_trace(plan_result=None, coverage_results=None, scan_result=None):
    """报告导出前的统一溯源硬断言（plan / coverage / scan 三条来源都查）。

    scan 通路的逐件结果同样承载 trace——**不得**因为它在 `scan_result.items`
    而非 `coverage_results` 就跳过断言（否则批量报告可带半溯源产出）。
    """
    out = {}
    if plan_result is not None:
        out["plan"] = assert_plan_trace(plan_result)
    coverage = list(coverage_results or [])
    if scan_result is not None:
        coverage.extend(scan_result.items)
    if coverage:
        out["coverage"] = [assert_coverage_trace(r) for r in coverage]
    return out
