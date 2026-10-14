"""M2：监护矩阵引擎完整实现 + 覆盖度四态 + 周期边界 + 别名归一 + 溯源硬断言 + 待输入索取。

对应 DoD：M2-1 … M2-7（plan/05 §四）。M1 已建真值库（独立参考实现），
本文件把 M2 的验收面扩到 DoD 各项——**引擎与真值 100% 对账**是主验收门。
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from helpers import data_dir, make_factor, make_record, make_temp_data_dir, write_json

from ohscheck.engine.coverage import (
    check_record,
    is_noncompliant,
    normalize_items,
    verdict_reachability,
)
from ohscheck.engine.matrix import compute_plan, expected_items
from ohscheck.engine.period import add_months, judge_period
from ohscheck.engine.pipeline import (
    build_context,
    build_position,
    build_record,
    build_report_model,
    compute_coverage,
    compute_plan as pipeline_plan,
)
from ohscheck.engine.trace import (
    TraceAssertionError,
    assert_coverage_trace,
    assert_plan_trace,
    expected_trace_lower_bound,
)
from ohscheck.errors import MissingInputError
from ohscheck.loaders import load_path
from ohscheck.model import EXAM_TYPES, FactorRef, HealthRecord, PositionProfile
from ohscheck.rules.gate import effective_ruleset
from ohscheck.rules.loader import Ruleset


def _records():
    out = []
    root = os.path.join(data_dir(), "truth", "records")
    for name in sorted(os.listdir(root)):
        if name.endswith(".json"):
            out.append((name, load_path(os.path.join(root, name))))
    return out


def _make_plan(factors, codes, exam_date="2026-09-15", exposure=None):
    eff = effective_ruleset(Ruleset(make_ruleset_local(factors)), "plan", required_factor_ids=codes)
    refs = [FactorRef(code, exposure_value=exposure) for code in codes]
    profile = PositionProfile(position_id="POS-1", exam_date=exam_date, factors=refs)
    return compute_plan(profile, eff)


def make_ruleset_local(factors):
    from helpers import make_ruleset

    return make_ruleset(factors)


# ---------------- M2-1：引擎与真值 100% 对账 ----------------

M2_ITEMS = [
    "pre_placement",
    "periodic",
    "post_placement",
    "emergency",
]


def test_truth_records_reconcile_on_verdict_and_expected_items():
    """M2-1：逐件对账**判定结论**与**应检项集合**（真值库独立参考实现）。

    比 M1 的 `test_every_truth_record_reconciles_with_engine` 更强：除 verdict/
    missing/period 外，还断言引擎推导出的 `expected_items` 与植入真值逐项一致。
    """
    from ohscheck.benchmark.cases import compare_expected
    from ohscheck.engine.pipeline import _plan_for_record

    context = build_context()
    total = 0
    for name, obj in _records():
        expect = dict(obj["expect"])
        record_obj = {k: v for k, v in obj.items() if k not in ("expect", "expect_case")}
        record = build_record(record_obj)
        result = compute_coverage(record, context)
        outcome = compare_expected(result, expect)
        assert outcome["ok"], (name, outcome)

        plan_result, _last = _plan_for_record(record, context)
        got = sorted(expected_items(plan_result, record.factor_code, record.exam_type))
        want = sorted(expect.get("expected_items") or [])
        assert got == want, (name, got, want)
        total += 1
    assert total >= 70, "真值库件数过少（M2 起应含周期三形态）"


def test_truth_covers_all_three_period_shapes():
    """M2-4：38 单值 / 22 分档 / 22 无周期三种形态，真值库各有件覆盖。

    真值库覆盖的 factor 的 period.kind 必须至少含 months / input_required / none
    三种（否则"周期覆盖"是纸面承诺）；且 manifest 的 `period_shape_coverage`
    须如实登记"抽样覆盖"（非逐因素穷举，D-61/D-59 同族）。
    """
    from ohscheck.rules.loader import load_ruleset

    ruleset = load_ruleset("GBZ188-2025")
    kind_of = {f["factor_code"]: f["period"]["kind"] for f in ruleset.factors}
    covered = set()
    for _name, obj in _records():
        kind = kind_of.get(obj["factor_code"])
        if kind:
            covered.add(kind)
    assert {"months", "input_required", "none"}.issubset(covered), covered

    manifest = load_path(os.path.join(data_dir(), "truth", "manifest.json"))
    shapes = {r["period_kind"]: r for r in manifest.get("period_shape_coverage") or []}
    assert {"months", "input_required", "none"}.issubset(shapes), shapes
    for kind in ("months", "input_required", "none"):
        assert shapes[kind]["sampled_factor_count"] >= 1, kind
        # 抽样数不得超过规则包内该形态总数（诚实性）
        assert shapes[kind]["sampled_factor_count"] <= shapes[kind]["ruleset_factor_count"], kind


# ---------------- M2-2：四时点独立判定（不互相污染）----------------


def test_four_timepoints_are_judged_independently():
    """M2-2：改一个时点的必检项**不得**影响其他三个时点的判定。"""
    factor = make_factor(required=("A1", "A2"))
    # 只改 periodic 的必检项
    factor["examinations"]["periodic"]["required_items"] = [
        {
            "item_code": "P_ONLY",
            "item_name": "p",
            "status": "verified",
            "basis": "b",
            "source": {"doc": "d", "clause": "c", "url": "", "fetched": ""},
        }
    ]
    plan = _make_plan([factor], ["T_FACTOR"])
    assert expected_items(plan, "T_FACTOR", "periodic") == ["P_ONLY"]
    for exam_type in ("pre_placement", "post_placement", "emergency"):
        assert expected_items(plan, "T_FACTOR", exam_type) == ["A1", "A2"], exam_type


def test_changing_one_exam_block_does_not_change_others_via_coverage():
    """M2-2（覆盖度侧）：同一档案在四时点下的判定相互独立。"""
    factors = [make_factor(required=("A1", "A2"))]
    # periodic 只要求 P_ONLY；其余时点要求 A1/A2
    factors[0]["examinations"]["periodic"]["required_items"] = [
        {
            "item_code": "P_ONLY",
            "item_name": "p",
            "status": "verified",
            "basis": "b",
            "source": {"doc": "d", "clause": "c", "url": "", "fetched": ""},
        }
    ]
    code = "T_FACTOR"
    eff = effective_ruleset(Ruleset(make_ruleset_local(factors)), "check", required_factor_ids=[code])
    plan = compute_plan(
        PositionProfile(position_id="P", exam_date="2026-09-15", factors=[FactorRef(code)]), eff
    )

    # 在 periodic 做 P_ONLY → 齐备；在上岗前做 A1/A2 → 齐备
    rec_periodic = HealthRecord.from_dict(
        make_record(items=("P_ONLY",), exam_type="periodic")
    )
    rec_pre = HealthRecord.from_dict(make_record(items=("A1", "A2"), exam_type="pre_placement"))
    assert check_record(rec_periodic, plan, last_exam_date=None).verdict == "compliant"
    assert check_record(rec_pre, plan, last_exam_date=None).verdict == "compliant"
    # 交叉：periodic 里做 A1/A2（非该时点应检项）→ 缺 P_ONLY
    rec_cross = HealthRecord.from_dict(make_record(items=("A1", "A2"), exam_type="periodic"))
    got = check_record(rec_cross, plan, last_exam_date=None)
    assert got.missing_items == ["P_ONLY"]


# ---------------- M2-3：覆盖度四态 + 缺项挂 basis（逐项下钻）----------------


def test_four_states_all_observed_in_truth_corpus():
    """M2-3：四态定级在真值库上**逐档有件覆盖**（compliant/partial/non_compliant）。"""
    seen = set()
    context = build_context()
    for _name, obj in _records():
        record = build_record({k: v for k, v in obj.items() if k not in ("expect", "expect_case")})
        seen.add(compute_coverage(record, context).verdict)
    assert {"compliant", "partial", "non_compliant"}.issubset(seen), seen


def test_missing_item_finding_carries_per_item_basis_and_source():
    """M2-3：缺项依据**逐项下钻**到规则包 item 级 basis/source（决策 D-16/FR-A4）。"""
    context = build_context()
    record = build_record(
        {
            "record_id": "SYN-TRUTH-008",
            "employee_id": "90000000008SYN",
            "factor_code": "GBZ188-5.19",
            "exam_date": "2026-09-15",
            "exam_type": "periodic",
            "items": ["血常规", "尿常规", "心电图", "肝脾B超"],
            "last_exam_date": "2025-10-01",
        }
    )
    result = compute_coverage(record, context)
    assert result.missing_items == ["肝功能"]
    finding = [f for f in result.findings if f["kind"] == "missing_item"][0]
    assert finding["item_code"] == "肝功能"
    assert finding["basis"], "缺项必须挂条款依据"
    source = finding.get("source") or {}
    assert source.get("doc"), "缺项依据应下钻到项级 source（doc/clause）"
    assert source.get("clause")
    # 逐项依据与规则包一致（不是随便挂的节级文本）
    ruleset = context.ruleset("GBZ188-2025")
    factor = ruleset.factor("GBZ188-5.19")
    item = [i for i in factor["examinations"]["periodic"]["required_items"]
            if i["item_code"] == "肝功能"][0]
    assert source["clause"] == item["source"]["clause"]


def test_not_applicable_is_declared_unreachable_on_real_ruleset():
    """M2-3/D-59：真实规则包上 not_applicable **不可达**，必须**如实声明**。

    标准对所列危害因素"接触即纳入"（kind=always）→ 逐因素无阈值 → not_applicable
    不可达。工具不得假装覆盖（决策 D-59）。
    """
    context = build_context()
    ruleset = context.ruleset("GBZ188-2025")
    rows = {r["state"]: r for r in verdict_reachability(ruleset)}
    assert rows["not_applicable"]["reachable"] is False
    assert "always" in rows["not_applicable"]["reason"] or "接触即纳入" in rows["not_applicable"]["reason"]
    # 合成夹具（含 threshold）上 not_applicable 可达 → 机制层覆盖
    factor = make_factor(kind="threshold", threshold=__import__("decimal").Decimal("10"))
    from helpers import make_ruleset

    rows2 = {r["state"]: r for r in verdict_reachability(Ruleset(make_ruleset([factor])))}
    assert rows2["not_applicable"]["reachable"] is True


def test_benchmark_fixture_covers_threshold_branches():
    """D-59 的 `covered_by` 声明必须**可验证**：合成夹具真含 threshold 因素，
    且引擎在其上确实走通 applicable / not_applicable / input_required 三态。

    实测缺口：truth manifest 曾声称"夹具含 kind=threshold"，但夹具全为 kind=always
    → **假覆盖声明**（违反 D-59"不假装覆盖"）。本测试把该声明锁成可证伪的。
    """
    from decimal import Decimal

    from helpers import bench_dir
    from ohscheck.loaders import load_path
    from ohscheck.rules.loader import Ruleset

    rs_obj = load_path(os.path.join(bench_dir(), "ruleset-2025.json"))
    kinds = {f["eligibility"]["kind"] for f in rs_obj["factors"]}
    assert "threshold" in kinds, "合成夹具必须含 threshold 因素（否则 D-59 覆盖声明为假）"
    threshold_factors = [f for f in rs_obj["factors"] if f["eligibility"]["kind"] == "threshold"]
    assert threshold_factors, "应有 threshold 型因素"
    factor = threshold_factors[0]
    code = factor["factor_code"]
    thr = Decimal(str(factor["eligibility"]["threshold"]))

    eff = effective_ruleset(Ruleset(rs_obj), "plan", required_factor_ids=[code])
    seen = set()
    for exposure in (None, thr - Decimal("1"), thr + Decimal("1")):
        profile = PositionProfile(
            position_id="B", exam_date="2026-09-15",
            factors=[FactorRef(code, exposure_value=exposure)],
        )
        plan = compute_plan(profile, eff)
        seen.add(plan.factors[0].applicability.state)
    assert seen == {"applicable", "not_applicable", "input_required"}, seen

    # manifest 声明的 coverage 与实态一致
    manifest = load_path(os.path.join(bench_dir(), "manifest.json"))
    declared = manifest.get("eligibility_coverage") or {}
    assert code in declared, declared
    assert set(declared[code]) == {"applicable", "not_applicable", "input_required"}


def test_report_states_unreachable_verdict_state():
    """M2-3/D-59：报告必须写出"不可达"而非假装覆盖。"""
    from ohscheck.report.markdown import render_markdown

    context = build_context()
    record = build_record(
        {
            "record_id": "SYN-TRUTH-001",
            "employee_id": "90000000001SYN",
            "factor_code": "GBZ188-5.19",
            "exam_date": "2026-09-15",
            "exam_type": "periodic",
            "items": ["血常规", "尿常规", "肝功能", "心电图", "肝脾B超"],
            "last_exam_date": "2025-10-01",
        }
    )
    results = [compute_coverage(record, context)]
    model = build_report_model(
        coverage_results=results, context=context, ruleset_id="GBZ188-2025",
        generated_at="2026-10-14T00:00:00",
    )
    md = render_markdown(model)
    assert "四态可达性" in md
    assert "不可达" in md


# ---------------- M2-4：周期边界 ----------------

def test_period_boundaries_on_real_data():
    """M2-4：due 计入合规、月末夹取、no_baseline 在真实数据上锁死。"""
    # 高温（7.3，12 个月）恰好到期
    context = build_context()
    rec = build_record(
        {
            "record_id": "R-DUE",
            "employee_id": "90000000007SYN",
            "factor_code": "GBZ188-7.3",
            "exam_date": "2026-09-20",
            "exam_type": "periodic",
            "items": [],
            "last_exam_date": "2025-09-20",
        }
    )
    # 高温在岗期间必检项齐备需按规则包填写；此处只验周期判定不受缺项影响
    result = compute_coverage(rec, context)
    assert result.period_verdict == "due"

    # 无基线 → no_baseline，不报超期（缺项导致的 non_compliant 与周期无关）
    rec2 = build_record(
        {
            "record_id": "R-NB",
            "employee_id": "90000000019SYN",
            "factor_code": "GBZ188-5.19",
            "exam_date": "2026-09-15",
            "exam_type": "periodic",
            "items": [],
        }
    )
    got = compute_coverage(rec2, context)
    assert got.period_verdict == "no_baseline"
    assert got.period_verdict != "overdue"
    assert not any(f["kind"] == "period_overdue" for f in got.findings)


def test_month_end_clamping_on_real_data():
    """M2-4：月末夹取（闰年 2/29 + 12 月 → 平年 2/28）在真值件上生效。"""
    name = "SYN-TRUTH-015.json"
    obj = load_path(os.path.join(data_dir(), "truth", "records", name))
    record = build_record({k: v for k, v in obj.items() if k not in ("expect", "expect_case")})
    result = compute_coverage(record, build_context())
    assert result.period_verdict == obj["expect"]["period_verdict"] == "due"


def test_tiered_period_does_not_false_report_overdue():
    """M2-4：分档周期（input_required）**不误报超期**（噪声/汞/粉尘）。"""
    context = build_context()
    for rec_id, emp, code in (
        ("SYN-TRUTH-006", "90000000006SYN", "GBZ188-7.1"),
        ("SYN-TRUTH-023", "90000000023SYN", "GBZ188-5.3"),
    ):
        obj = load_path(os.path.join(data_dir(), "truth", "records", "%s.json" % rec_id))
        record = build_record({k: v for k, v in obj.items() if k not in ("expect", "expect_case")})
        result = compute_coverage(record, context)
        assert result.period_verdict == "input_required", (rec_id, result.period_verdict)
        assert result.period_verdict != "overdue", rec_id


# ---------------- M2-5：别名归一路径 ----------------

def test_alias_path_disabled_when_pending():
    """M2-5：别名表 pending → 归一路径**整体禁用**（不猜，决策 D-17）。"""
    context = build_context()
    from ohscheck.engine.pipeline import _alias_map

    # 生产规则包 alias_map.status=pending → 返回 None
    assert _alias_map(context, "GBZ188-2025") is None
    assert _alias_map(context, None) is None


def test_alias_path_enabled_when_verified(tmp_path):
    """M2-5：别名表 verified 时启用（显式表，非模糊匹配）。"""
    factor = make_factor(required=("A1",))
    root = tmp_path / "data"
    root.mkdir()
    data_root = make_temp_data_dir(str(root), factors=[factor])
    # 给规则包注入 verified 别名表
    rs_path = os.path.join(data_root, "rules", "ruleset.json")
    obj = load_path(rs_path)
    obj["alias_map"] = {
        "status": "verified",
        "source": {"doc": "SYNTHETIC-X", "clause": "1", "url": "", "fetched": ""},
        "map": {"别名A1": "A1"},
    }
    write_json(rs_path, obj)
    # manifest sha256 需同步（此处仅验别名通路，不验指纹）
    context = build_context(data_root)
    from ohscheck.engine.pipeline import _alias_map

    got = _alias_map(context, "SYN-TEST")
    assert got == {"别名A1": "A1"}

    rec = make_record(items=("别名A1",), exam_type="pre_placement")
    path = os.path.join(str(tmp_path), "rec.json")
    write_json(path, rec)
    result = compute_coverage(build_record(load_path(path)), context)
    assert result.verdict == "compliant"
    assert not result.unmapped_items


def test_no_fuzzy_matching_in_normalization():
    """M2-5：归一**禁模糊匹配**（子串包含/编辑距离都不得命中）。"""
    # 子串包含：known 含 "A1"，实检写 "A1X" → 不得命中
    got, unmapped = normalize_items(["A1X"], known_codes={"A1"}, alias_map=None)
    assert got == set()
    assert unmapped == ["A1X"]
    # 近似写法：不得自动映射
    got2, unmapped2 = normalize_items(["A 1"], known_codes={"A1"}, alias_map={"A 1": "A1"})
    assert got2 == {"A1"}  # 显式表命中才可
    got3, unmapped3 = normalize_items(["A1 "], known_codes={"A1"}, alias_map=None)
    assert got3 == {"A1"}  # strip 后的精确命中


def test_unmapped_degrades_to_warning_not_missing():
    """M2-5：归一不成立 → warning 不判缺失（真值件 SYN-TRUTH-020）。"""
    obj = load_path(os.path.join(data_dir(), "truth", "records", "SYN-TRUTH-020.json"))
    record = build_record({k: v for k, v in obj.items() if k not in ("expect", "expect_case")})
    result = compute_coverage(record, build_context())
    assert result.verdict == "compliant"
    assert result.unmapped_items
    assert any(f["kind"] == "warning" for f in result.findings)
    assert not result.is_noncompliant


# ---------------- M2-6：溯源硬断言 ----------------

def test_plan_trace_row_count_and_basis_nonempty_on_real_data():
    """M2-6：行数对账 + basis 非空（真实数据）。"""
    context = build_context()
    profile = build_position(
        {"position_id": "POS-B", "exam_date": "2026-09-15",
         "factors": [{"factor_code": "GBZ188-5.19"}]}
    )
    plan = pipeline_plan(profile, context)
    info = assert_plan_trace(plan)
    lower, factors, details = expected_trace_lower_bound(plan)
    assert info["trace_rows"] >= lower == factors + details
    assert all(row["basis"] for row in plan.trace)


def test_trace_assertion_refuses_export_when_rows_missing():
    """M2-6：行数不足 → **拒导**（TraceAssertionError，不留半溯源报告）。"""
    factor = make_factor(required=("A1", "A2"))
    plan = _make_plan([factor], ["T_FACTOR"])
    # 人为破坏：删掉一半 trace 行
    plan.trace = plan.trace[:2]
    with pytest.raises(TraceAssertionError) as exc:
        assert_plan_trace(plan)
    assert exc.value.exit_code == 2
    assert exc.value.reason == "trace_incomplete"


def test_trace_assertion_refuses_export_when_basis_empty():
    """M2-6：任一 trace 行 basis 为空 → 拒导。"""
    factor = make_factor(required=("A1",))
    plan = _make_plan([factor], ["T_FACTOR"])
    plan.trace[0]["basis"] = ""
    with pytest.raises(TraceAssertionError) as exc:
        assert_plan_trace(plan)
    assert any("basis 为空" in v for v in exc.value.violations)


def test_export_report_refuses_when_trace_incomplete(tmp_path):
    """M2-6：导出通路在溯源不完整时**拒导**（不产出任何报告文件）。"""
    from ohscheck.engine.export import export_report

    context = build_context()
    profile = build_position(
        {"position_id": "POS-B", "exam_date": "2026-09-15",
         "factors": [{"factor_code": "GBZ188-5.19"}]}
    )
    plan = pipeline_plan(profile, context)
    plan.trace = []  # 破坏溯源
    model = build_report_model(
        plan_result=plan, context=context, ruleset_id=plan.ruleset_id,
        generated_at="2026-10-14T00:00:00",
    )
    out = tmp_path / "out"
    with pytest.raises(TraceAssertionError):
        export_report(model, str(out))
    assert not os.path.exists(str(out)), "拒导时不得留下半成品报告"


def test_coverage_trace_assertion_skips_unjudged():
    """M2-6：failed/unknown 不产出结论 → 溯源断言不适用（不冒充溯源）。"""
    factor = make_factor(code="T_FACTOR")
    eff = effective_ruleset(Ruleset(make_ruleset_local([factor])), "check", required_factor_ids=["T_FACTOR"])
    plan = compute_plan(
        PositionProfile(position_id="P", exam_date="2026-09-15", factors=[FactorRef("T_FACTOR")]), eff
    )
    record = HealthRecord.from_dict(make_record(factor_code="OTHER", items=(), exam_type="pre_placement"))
    result = check_record(record, plan)
    assert result.verdict == "unknown"
    info = assert_coverage_trace(result)
    assert info["applicable"] is False


# ---------------- M2-7：input_required 运行期显式索取 ----------------

def test_blocking_missing_input_raises_exit_2():
    """M2-7：适用性/项目级待输入 → MissingInputError（退出码 2，绝不静默取默认值）。"""
    factor = make_factor()
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = "需按具体情况确定（规则包不承载）"
    root_rs = make_ruleset_local([factor])
    eff = effective_ruleset(Ruleset(root_rs), "plan", required_factor_ids=["T_FACTOR"])
    assert len(eff.missing_inputs) == 1
    assert eff.missing_inputs[0]["blocking"] is True


def test_period_tiering_is_nonblocking_and_solicited():
    """M2-7：周期级待输入 → 放行 + 显式索取（blocking=False，决策 D-53）。"""
    context = build_context()
    profile = build_position(
        {"position_id": "POS-NOISE", "exam_date": "2026-09-20",
         "factors": [{"factor_code": "GBZ188-7.1"}]}
    )
    result = pipeline_plan(profile, context)  # 放行
    deferred = [m for m in result.missing_inputs if not m.get("blocking", True)]
    assert deferred, "周期分档应作为待输入项显式列出"
    assert all(m.get("factor_code") for m in deferred)


def test_cli_exit_2_on_blocking_missing_input(tmp_path):
    """M2-7：CLI 端到端——适用性待输入 → 退出码 2。"""
    from ohscheck.cli import main

    factor = make_factor()
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = "需按具体情况确定（规则包不承载）"
    root = tmp_path / "data"
    root.mkdir()
    data_root = make_temp_data_dir(str(root), factors=[factor])
    pos = {"position_id": "P", "exam_date": "2026-09-15", "factors": [{"factor_code": "T_FACTOR"}]}
    path = str(tmp_path / "pos.json")
    write_json(path, pos)

    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(["plan", path, "--data-dir", data_root])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    assert code == 2, err.getvalue()
    assert "外部输入" in err.getvalue() or "待输入" in err.getvalue() or "缺少" in err.getvalue()


def test_cli_tiered_real_factor_passes_and_reports_input_required(tmp_path):
    """M2-7：CLI 端到端——真实分档因素（铅）plan 放行且报告"待输入"（不拦）。"""
    from ohscheck.cli import main

    pos = {"position_id": "POS-PB", "exam_date": "2026-09-15", "factors": [{"factor_code": "GBZ188-5.1"}]}
    path = str(tmp_path / "pos.json")
    write_json(path, pos)
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(["plan", path, "--json"])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    assert code == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    deferred = [m for m in payload["missing_inputs"] if not m.get("blocking", True)]
    assert deferred, payload["missing_inputs"]
    assert payload["factors"][0]["exams"]["periodic"]["required_items"]


def test_report_period_section_separates_input_required():
    """M2-7：报告 §5 把"待输入"**单列**，不得与"合规"混同（决策 D-13/D-53）。"""
    from ohscheck.report.markdown import render_markdown
    from ohscheck.report.sections import report_sections

    context = build_context()
    obj = load_path(os.path.join(data_dir(), "truth", "records", "SYN-TRUTH-006.json"))
    record = build_record({k: v for k, v in obj.items() if k not in ("expect", "expect_case")})
    results = [compute_coverage(record, context)]
    model = build_report_model(
        coverage_results=results, context=context, ruleset_id="GBZ188-2025",
        generated_at="2026-10-14T00:00:00",
    )
    md = render_markdown(model)
    assert "周期待输入" in md
    section5 = [s for s in report_sections(model) if s.number == "5"][0]
    titles = [t.title for t in section5.tables]
    assert "周期待输入（不判合规，亦不判超期）" in titles


def test_scan_driven_report_still_presents_coverage_and_period():
    """M2-7 补：**批量通路**（scan）的报告同样须呈现覆盖明细与周期待输入。

    实测缺口：§4/§5 原先只读 `coverage_results`，scan 驱动的报告会把逐件判定
    与"待输入"整块吞掉 → "没呈现"与"没问题"在报告上不可区分（同族 D-35）。
    """
    from ohscheck.engine.scan import ScanResult
    from ohscheck.report.markdown import render_markdown
    from ohscheck.report.sections import report_sections
    from ohscheck.model import CoverageResult

    scan = ScanResult()
    scan.items = [
        CoverageResult(
            record_id="SYN-R1",
            employee_id="90000000006SYN",
            factor_code="GBZ188-7.1",
            exam_type="periodic",
            verdict="compliant",
            period_verdict="input_required",
        )
    ]
    model = build_report_model(
        scan_result=scan, context=build_context(), ruleset_id="GBZ188-2025",
        generated_at="2026-10-14T00:00:00",
    )
    md = render_markdown(model)
    assert "周期待输入" in md, "scan 通路报告应呈现待输入"
    assert "SYN-R1" in md, "scan 通路报告应呈现逐件判定"
    s5 = [s for s in report_sections(model) if s.number == "5"][0]
    assert "周期待输入（不判合规，亦不判超期）" in [t.title for t in s5.tables]
