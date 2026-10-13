"""基准用例的真值语义（**单一实现源**，决策 D-20/_05 §2.4）。

测试与基准**共用**本模块的对账函数——否则会出现"基准说达标、测试说不过"的双口径漂移。
"""

from __future__ import annotations

from ..model import NONCOMPLIANT_VERDICTS, VERDICT_COMPLIANT, VERDICT_NOT_APPLICABLE


def observed_nonpass(coverage_result):
    """一份核查结果的"非 pass"观测集合（对账用）。

    非 pass = fail ∪ unknown；not_applicable **排除在比较之外**（决策 D-22：
    不适用是"不适用"，不是"缺失"；纳入会制造假"已修复"）。
    """
    if coverage_result.verdict == VERDICT_NOT_APPLICABLE:
        return set()
    out = set()
    for item in coverage_result.missing_items:
        out.add(("missing", item))
    if coverage_result.verdict in NONCOMPLIANT_VERDICTS:
        out.add(("verdict", coverage_result.verdict))
    if coverage_result.period_verdict == "overdue":
        out.add(("period", "overdue"))
    if coverage_result.verdict == "unknown":
        out.add(("unknown", coverage_result.failed_reason or "unknown"))
    return out


def expected_nonpass(expect):
    """从真值记录的 expect 段取期望非 pass 集合（同一口径）。"""
    out = set()
    for item in expect.get("missing_items") or []:
        out.add(("missing", item))
    if expect.get("verdict") in NONCOMPLIANT_VERDICTS:
        out.add(("verdict", expect["verdict"]))
    if expect.get("period_verdict") == "overdue":
        out.add(("period", "overdue"))
    # also_expect：同一注入隐含的其余结论（plan/05 §2.4）
    for extra in expect.get("also_expect") or []:
        if extra.get("kind") == "missing":
            out.add(("missing", extra.get("item_code")))
        elif extra.get("kind") == "verdict":
            out.add(("verdict", extra.get("verdict")))
        elif extra.get("kind") == "period":
            out.add(("period", extra.get("verdict")))
    return out


def compare_expected(coverage_result, expect):
    """对账一份结果与期望。

    Returns:
        dict: {ok, missing_false_negative, extra_false_positive,
               verdict_ok, period_ok}
    """
    observed = observed_nonpass(coverage_result)
    expected = expected_nonpass(expect)

    fn = sorted(expected - observed)  # 漏报
    fp = sorted(observed - expected)  # 误报

    verdict_ok = coverage_result.verdict == expect.get("verdict")
    period_ok = True
    if expect.get("period_verdict") is not None:
        period_ok = coverage_result.period_verdict == expect.get("period_verdict")

    return {
        "ok": not fn and not fp and verdict_ok and period_ok,
        "missing_false_negative": fn,
        "extra_false_positive": fp,
        "verdict_ok": verdict_ok,
        "period_ok": period_ok,
        "observed_verdict": coverage_result.verdict,
        "expected_verdict": expect.get("verdict"),
    }


def is_clean_expect(expect):
    """真值是否声明为"应零命中"的干净档案（误报对照集，FR-E4）。"""
    return bool(expect.get("should_be_clean"))


def observed_is_clean(coverage_result):
    """观测是否零命中（无缺项、无超期、结论为符合）。"""
    return (
        coverage_result.verdict == VERDICT_COMPLIANT
        and not coverage_result.missing_items
        and coverage_result.period_verdict != "overdue"
    )
