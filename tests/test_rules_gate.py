"""规则层：schema 不变式、status 门控分作用域、版本锚定。

对应 DoD：M0-5、M0-6、M0-7。
"""

from __future__ import annotations

import datetime as _dt

import pytest

from helpers import make_factor, make_manifest, make_ruleset

from ohscheck.errors import AmbiguousYearError, GateBlocked, InputError
from ohscheck.rules.gate import effective_ruleset, pending_report
from ohscheck.rules.loader import Manifest, Ruleset
from ohscheck.rules.schema import validate_manifest, validate_ruleset
from ohscheck.rules.version import resolve_ruleset_id


# ---------------- schema 不变式（M0-5）----------------


def test_valid_ruleset_passes():
    validate_ruleset(make_ruleset())


def test_pending_with_value_is_rejected():
    """pending 却填了值 → 拒绝（防"先填大概值再标待核对"）。"""
    factor = make_factor(period_status="pending")
    # 违规形态：单值月数周期（kind=months）标 pending 却带值。
    # kind 也须改回 months——kind=pending 本不承载值，填值不触发该校验。
    factor["period"]["kind"] = "months"
    factor["period"]["value"] = 12
    with pytest.raises(InputError) as e:
        validate_ruleset(make_ruleset([factor]))
    assert "pending" in str(e.value)


def test_verified_with_null_value_is_rejected():
    """verified 但值为 null → 拒绝（不许半核对的悬空值）。"""
    factor = make_factor()
    factor["period"]["value"] = None  # 违规：verified 但无值
    with pytest.raises(InputError):
        validate_ruleset(make_ruleset([factor]))


def test_verified_without_source_is_rejected():
    factor = make_factor()
    factor["period"]["source"] = {"doc": "", "clause": "", "url": "", "fetched": ""}
    with pytest.raises(InputError) as e:
        validate_ruleset(make_ruleset([factor]))
    assert "source.doc" in str(e.value)


def test_input_required_needs_basis():
    factor = make_factor()
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = ""  # 违规：input_required 必须说明理由
    with pytest.raises(InputError) as e:
        validate_ruleset(make_ruleset([factor]))
    assert "basis" in str(e.value)


def test_synthetic_ruleset_must_not_claim_real_provenance():
    """合成夹具不得冒充真实标准出处（数据纪律）。"""
    rs = make_ruleset()
    rs["basis"]["doc_code"] = "GBZ 188—2025"  # 冒充真实标准
    with pytest.raises(InputError) as e:
        validate_ruleset(rs)
    assert "SYNTHETIC-" in str(e.value)


def test_synthetic_ruleset_must_not_have_issuer():
    rs = make_ruleset()
    rs["basis"]["issuer"] = "国家卫生健康委员会"
    with pytest.raises(InputError):
        validate_ruleset(rs)


def test_emergency_only_policy_rejects_optional_items_outside_emergency():
    """新标口径（删除上岗前/在岗期间/离岗时选检项）由**数据**声明。

    口径写在规则包的 optional_items_policy 字段里，不在代码里按版本号硬编码
    （零字面量门禁的口径要求）；emergency_only 时非应急时点不得有选检项。
    """
    factor = make_factor()
    factor["examinations"]["periodic"]["optional_items"] = [
        {"item_code": "X", "item_name": "X", "status": "verified",
         "basis": "", "source": {"doc": "SYNTHETIC-X", "clause": "1", "url": "", "fetched": ""}}
    ]
    with pytest.raises(InputError) as e:
        validate_ruleset(
            make_ruleset([factor], ruleset_id="SYN-2025", optional_items_policy="emergency_only")
        )
    assert "选检" in str(e.value)


def test_any_policy_allows_optional_items_anywhere():
    """旧版口径（any）允许各时点保留选检项——同一 schema，行为由数据决定。"""
    factor = make_factor()
    factor["examinations"]["periodic"]["optional_items"] = [
        {"item_code": "X", "item_name": "X", "status": "verified",
         "basis": "", "source": {"doc": "SYNTHETIC-X", "clause": "1", "url": "", "fetched": ""}}
    ]
    validate_ruleset(make_ruleset([factor], ruleset_id="SYN-2014", optional_items_policy="any"))


def test_emergency_keeps_optional_items_under_emergency_only_policy():
    """应急检查在 emergency_only 口径下仍保留选检项。"""
    factor = make_factor()
    factor["examinations"]["emergency"]["optional_items"] = [
        {"item_code": "X", "item_name": "X", "status": "verified",
         "basis": "", "source": {"doc": "SYNTHETIC-X", "clause": "1", "url": "", "fetched": ""}}
    ]
    validate_ruleset(
        make_ruleset([factor], ruleset_id="SYN-2025", optional_items_policy="emergency_only")
    )


def test_manifest_requires_benchmark_thresholds():
    """门槛是数据不是代码（决策 D-24）：manifest 缺门槛即拒绝。"""
    m = make_manifest()
    del m["benchmark_thresholds"]
    with pytest.raises(InputError) as e:
        validate_manifest(m)
    assert "benchmark_thresholds" in str(e.value)


# ---------------- 顶层 status = 整包完成度标签（迭代 D-4）----------------


def test_top_level_status_optional_and_validated():
    """顶层 status 可选；出现时必须在 {partial, scaffold} 内（标签，不参与门控）。"""
    rs = make_ruleset()
    assert "status" not in rs
    validate_ruleset(rs)  # 缺省合法（合成夹具与基准规则集不带该字段）

    for value in ("partial", "scaffold"):
        obj = make_ruleset()
        obj["status"] = value
        validate_ruleset(obj)

    bad = make_ruleset()
    bad["status"] = "verified"  # 条目级三态值不是整包标签
    with pytest.raises(InputError) as e:
        validate_ruleset(bad)
    assert "顶层 status" in str(e.value)
    assert "不参与门控" in str(e.value)


def test_production_rulesets_carry_expected_package_status():
    """生产两版规则包的顶层标签与留档一致（2025=partial / 2014=scaffold）。"""
    import json
    import os

    from helpers import data_dir

    for name, want in (("ruleset-2025.json", "partial"), ("ruleset-2014.json", "scaffold")):
        path = os.path.join(data_dir(), "rules", name)
        obj = json.loads(open(path, encoding="utf-8").read())
        assert obj.get("status") == want, name
        validate_ruleset(obj)


# ---------------- 门控分作用域（M0-6）----------------


def _eff(ruleset_obj, scope, codes=None):
    return effective_ruleset(Ruleset(ruleset_obj), scope, required_factor_ids=codes)


def test_gate_blocks_pending_in_full_scope():
    factor = make_factor(period_status="pending")
    with pytest.raises(GateBlocked) as e:
        _eff(make_ruleset([factor]), "plan", ["T_FACTOR"])
    assert e.value.exit_code == 2
    assert any("period" in b for b in e.value.blocked)


def test_gate_scope_isolation_pending_project_detail_does_not_block_compare():
    """scope 隔离：项目明细待核对不应阻断 compare（决策 D-12 的核心）。

    这是"门控按计算路径分作用域"的判据——只拦本次计算实际引用的条目。
    """
    factor = make_factor(exam_status="pending")  # 项目明细 pending，但因素本身 verified
    # plan/check 走 full 深度 → 应拦截
    with pytest.raises(GateBlocked):
        _eff(make_ruleset([factor]), "plan", ["T_FACTOR"])
    # compare 走 minimal 深度 → 放行（结构对照不依赖项目明细）
    eff = _eff(make_ruleset([factor]), "compare", ["T_FACTOR"])
    assert eff.ruleset_id == "SYN-TEST"


def test_gate_only_checks_referenced_factors():
    """只校验本次计算引用的因素，未被引用的 pending 因素不阻断。"""
    ok = make_factor(code="T_OK", fid="5.1.0")
    bad = make_factor(code="T_BAD", fid="5.2.0", period_status="pending")
    eff = _eff(make_ruleset([ok, bad]), "plan", ["T_OK"])
    assert eff.used_factor_codes == ["T_OK"]


def test_gate_rejects_unknown_factor_code():
    with pytest.raises(InputError):
        _eff(make_ruleset(), "plan", ["NOT_EXIST"])


def test_gate_rejects_unknown_scope():
    with pytest.raises(ValueError):
        _eff(make_ruleset(), "nope")


def test_input_required_passes_gate_but_is_reported():
    """第三态 input_required：放行门控，但必须被运行时显式索取（决策 D-13）。"""
    factor = make_factor()
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = "需按具体情况确定（规则包不承载）"
    eff = _eff(make_ruleset([factor]), "plan", ["T_FACTOR"])
    assert len(eff.missing_inputs) == 1
    assert eff.missing_inputs[0]["factor_code"] == "T_FACTOR"


def test_pending_report_does_not_raise():
    factor = make_factor(period_status="pending")
    pending, inputs = pending_report(Ruleset(make_ruleset([factor])), "plan")
    assert pending and not inputs


# ---------------- 版本锚定（M0-7）----------------


def _manifest():
    return Manifest(make_manifest())


def test_cutover_boundary_is_inclusive_of_after():
    m = _manifest()
    assert resolve_ruleset_id("2026-07-31", m) == "SYN-OLD"
    assert resolve_ruleset_id("2026-08-01", m) == "SYN-NEW"
    assert resolve_ruleset_id(_dt.date(2026, 8, 1), m) == "SYN-NEW"


def test_ambiguous_year_raises():
    """只给年度且该年度含切口日 → 报错不猜（决策 D-11）。"""
    with pytest.raises(AmbiguousYearError) as e:
        resolve_ruleset_id(2026, _manifest())
    assert e.value.exit_code == 2


def test_year_outside_cutover_year_resolves():
    m = _manifest()
    assert resolve_ruleset_id(2025, m) == "SYN-OLD"
    assert resolve_ruleset_id(2027, m) == "SYN-NEW"
