"""判定层：矩阵推导、覆盖度四态、周期边界。

对应 DoD：M0-9（骨架可跑 + 机制正确）+ M2-4（周期边界已在此锁死）。
"""

from __future__ import annotations

import pytest

from helpers import make_factor, make_record, make_ruleset

from ohscheck.engine.coverage import check_record, normalize_items
from ohscheck.engine.matrix import expected_items, compute_plan
from ohscheck.engine.period import add_months, is_period_noncompliant, judge_period
from ohscheck.model import (
    FactorRef,
    HealthRecord,
    PositionProfile,
    VERDICT_COMPLIANT,
    VERDICT_NON_COMPLIANT,
    VERDICT_NOT_APPLICABLE,
    VERDICT_PARTIAL,
    VERDICT_UNKNOWN,
)
from ohscheck.rules.gate import effective_ruleset
from ohscheck.rules.loader import Ruleset


def _plan(factors, codes, exam_date="2026-09-15", exposure=None):
    eff = effective_ruleset(Ruleset(make_ruleset(factors)), "plan", required_factor_ids=codes)
    refs = []
    for code in codes:
        refs.append(FactorRef(code, exposure_value=exposure))
    profile = PositionProfile(position_id="POS-1", exam_date=exam_date, factors=refs)
    return compute_plan(profile, eff)


def _check(factors, record_obj, last=None, alias_map=None):
    factors_by_code = {f["factor_code"]: f for f in factors}
    code = record_obj["factor_code"]
    eff = effective_ruleset(Ruleset(make_ruleset(factors)), "check", required_factor_ids=[code])
    profile = PositionProfile(
        position_id="POS-1", exam_date=record_obj["exam_date"],
        factors=[FactorRef(code)],
    )
    plan = compute_plan(profile, eff)
    record = HealthRecord.from_dict(record_obj)
    return check_record(record, plan, alias_map=alias_map, last_exam_date=last)


# ---------------- 周期：月加法与边界 ----------------


def test_add_months_clamps_month_end():
    """月末夹取：1/31 + 1 月 = 2/28（平年）。"""
    assert str(add_months("2026-01-31", 1)) == "2026-02-28"
    assert str(add_months("2024-01-31", 1)) == "2024-02-29"  # 闰年
    assert str(add_months("2026-12-31", 2)) == "2027-02-28"
    assert str(add_months("2026-03-15", 12)) == "2027-03-15"


def test_period_due_day_counts_as_compliant():
    """到期当日检查计入合规（决策 D-18）。"""
    rule = {"kind": "months", "value": 12}
    got = judge_period(rule, "2025-09-15", "2026-09-15")
    assert got["verdict"] == "due"
    assert got["due_date"] == "2026-09-15"
    assert not is_period_noncompliant(got["verdict"])


def test_period_one_day_late_is_overdue():
    rule = {"kind": "months", "value": 12}
    assert judge_period(rule, "2025-09-15", "2026-09-14")["verdict"] == "compliant"
    assert judge_period(rule, "2025-09-15", "2026-09-16")["verdict"] == "overdue"
    assert is_period_noncompliant("overdue")


def test_period_no_baseline_is_not_overdue():
    """首次检查无基线 → 不报超期（决策 D-18）。"""
    got = judge_period({"kind": "months", "value": 12}, None, "2026-09-15")
    assert got["verdict"] == "no_baseline"
    assert not is_period_noncompliant(got["verdict"])


def test_period_none_kind_is_not_applicable():
    assert judge_period({"kind": "none"}, "2025-01-01", "2026-09-15")["verdict"] == "not_applicable"


# ---------------- 矩阵推导 ----------------


def test_plan_produces_expected_items_for_four_exam_types():
    plan = _plan([make_factor(required=("A1", "A2"))], ["T_FACTOR"])
    for exam_type in ("pre_placement", "periodic", "post_placement", "emergency"):
        assert sorted(expected_items(plan, "T_FACTOR", exam_type)) == ["A1", "A2"]


def test_threshold_below_reference_is_not_applicable():
    """低于阈值 → 不适用（决策 D-22：不适用 ≠ 违规）。"""
    from decimal import Decimal

    factor = make_factor(kind="threshold", threshold=Decimal("10"), comparator=">=")
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("3"))
    result = plan.factors[0]
    assert result.applicability.state == "not_applicable"
    assert result.exams == {}  # 不适用 → 不产出应检清单


def test_threshold_at_or_above_reference_is_applicable():
    from decimal import Decimal

    factor = make_factor(kind="threshold", threshold=Decimal("10"), comparator=">=")
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("10"))
    assert plan.factors[0].applicability.state == "applicable"


def test_missing_exposure_requests_input_instead_of_guessing():
    """缺接触水平 → 记 missing_inputs，**绝不静默取默认值**（决策 D-13）。"""
    from decimal import Decimal

    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    plan = _plan([factor], ["T_FACTOR"], exposure=None)
    assert plan.factors[0].applicability.state == "input_required"
    assert len(plan.missing_inputs) == 1


def test_trace_covers_every_required_item():
    """溯源硬断言：每条应检项都有溯源行且挂条款依据（FR-A4）。"""
    plan = _plan([make_factor(required=("A1", "A2"))], ["T_FACTOR"])
    targets = {row["target"] for row in plan.trace}
    for exam_type in ("pre_placement", "periodic", "post_placement", "emergency"):
        for code in ("A1", "A2"):
            assert "POS-1/T_FACTOR/%s/%s" % (exam_type, code) in targets
    assert all(row["basis"] for row in plan.trace)


def test_supplementary_items_do_not_enter_expected_set():
    """补充项目不进判定（决策 D-16）——缺失不报。"""
    factor = make_factor(required=("A1",))
    factor["examinations"]["periodic"]["supplementary_items"] = [
        {"item_code": "SUP1", "item_name": "S", "status": "verified",
         "basis": "", "source": {"doc": "SYNTHETIC-X", "clause": "1", "url": "", "fetched": ""}}
    ]
    plan = _plan([factor], ["T_FACTOR"])
    assert expected_items(plan, "T_FACTOR", "periodic") == ["A1"]


# ---------------- 覆盖度四态 ----------------


def test_verdict_compliant_when_all_required_present_and_period_ok():
    factors = [make_factor(required=("A1", "A2"))]
    rec = make_record(items=("A1", "A2"), exam_type="pre_placement")
    result = _check(factors, rec)
    assert result.verdict == VERDICT_COMPLIANT


def test_verdict_partial_when_one_required_missing():
    factors = [make_factor(required=("A1", "A2"))]
    rec = make_record(items=("A1",), exam_type="pre_placement")
    result = _check(factors, rec)
    assert result.verdict == VERDICT_PARTIAL
    assert result.missing_items == ["A2"]


def test_verdict_non_compliant_when_no_required_done():
    """必检项一项未做 → 不符合（定级边界）。"""
    factors = [make_factor(required=("A1", "A2"))]
    rec = make_record(items=(), exam_type="pre_placement")
    result = _check(factors, rec)
    assert result.verdict == VERDICT_NON_COMPLIANT
    assert result.missing_items == ["A1", "A2"]


def test_verdict_overdue_makes_partial_even_if_items_complete():
    factors = [make_factor(required=("A1",), months=12)]
    rec = make_record(items=("A1",), exam_date="2026-09-15", exam_type="periodic")
    result = _check(factors, rec, last="2024-01-01")
    assert result.verdict == VERDICT_PARTIAL
    assert result.period_verdict == "overdue"


def test_not_applicable_is_not_noncompliant():
    """不适用不计违规（决策 D-22）。"""
    from decimal import Decimal

    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    eff = effective_ruleset(
        Ruleset(make_ruleset([factor])), "check", required_factor_ids=["T_FACTOR"]
    )
    profile = PositionProfile(
        position_id="P", exam_date="2026-09-15",
        factors=[FactorRef("T_FACTOR", exposure_value=Decimal("1"))],
    )
    plan = compute_plan(profile, eff)
    record = HealthRecord.from_dict(make_record(items=(), exam_type="pre_placement"))
    result = check_record(record, plan)
    assert result.verdict == VERDICT_NOT_APPLICABLE
    assert not result.is_noncompliant


def test_unmapped_item_is_warning_not_missing():
    """别名归一不成立 → 降级 warning，不硬判缺失（决策 D-17）。"""
    factors = [make_factor(required=("A1",))]
    rec = make_record(items=("A1", "某种写法"), exam_type="pre_placement")
    result = _check(factors, rec)
    assert result.verdict == VERDICT_COMPLIANT  # 不判缺失
    assert result.unmapped_items == ["某种写法"]
    assert any(f["kind"] == "warning" for f in result.findings)


def test_alias_map_normalizes_when_enabled():
    factors = [make_factor(required=("A1",))]
    rec = make_record(items=("别名A1",), exam_type="pre_placement")
    result = _check(factors, rec, alias_map={"别名A1": "A1"})
    assert result.verdict == VERDICT_COMPLIANT
    assert not result.unmapped_items


def test_normalize_items_exact_hit_works_without_alias_map():
    """精确命中与别名表是否启用无关（否则会把规范代码本身记成 unmapped）。"""
    got, unmapped = normalize_items(["A1"], known_codes={"A1"}, alias_map=None)
    assert got == {"A1"}
    assert unmapped == []


def test_unknown_factor_yields_failed_not_verdict():
    """因素不识别 → 不产出 verdict，记 failed + 原因码（失败件 ≠ 违规）。"""
    factors = [make_factor(code="T_FACTOR")]
    eff = effective_ruleset(
        Ruleset(make_ruleset(factors)), "check", required_factor_ids=["T_FACTOR"]
    )
    profile = PositionProfile(
        position_id="P", exam_date="2026-09-15", factors=[FactorRef("T_FACTOR")]
    )
    plan = compute_plan(profile, eff)
    rec_obj = make_record(factor_code="OTHER_FACTOR", items=("A1",), exam_type="pre_placement")
    record = HealthRecord.from_dict(rec_obj)
    result = check_record(record, plan)
    assert result.failed_reason == "unknown_factor"
    assert not result.is_noncompliant
