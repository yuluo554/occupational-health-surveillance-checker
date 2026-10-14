"""真值库：合成监护档案对账、误报对照集、门控作用域（真实数据）。

对应 DoD：M1-4（合成档案 + 植入真值 + --check 位级一致）、
M1-5（误报对照集显式声明）、M1-7（门控作用域在真实数据上验证）。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from helpers import data_dir, repo_root

from ohscheck.benchmark.cases import compare_expected, is_clean_expect
from ohscheck.engine.pipeline import (
    build_context,
    build_position,
    build_record,
    compute_coverage,
    compute_plan,
)
from ohscheck.errors import GateBlocked, MissingInputError
from ohscheck.loaders import load_path
from ohscheck.model import FactorRef, PositionProfile
from ohscheck.rules.gate import effective_ruleset
from ohscheck.rules.loader import load_ruleset


def _truth_dir():
    return os.path.join(data_dir(), "truth")


def _records():
    out = []
    root = os.path.join(_truth_dir(), "records")
    for name in sorted(os.listdir(root)):
        if name.endswith(".json"):
            out.append((name, load_path(os.path.join(root, name))))
    return out


# ---------------- M1-4：冻结产物位级一致 ----------------


def test_frozen_truth_regenerates_byte_identical():
    """合成真值库为生成器冻结产物；再生成必须逐字节一致（决策 D-26）。"""
    root = repo_root()
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "gen_synthetic.py"), "--check"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert "FROZEN_TRUTH_OK" in out


def test_truth_manifest_declares_seed_and_ruleset():
    manifest = load_path(os.path.join(_truth_dir(), "manifest.json"))
    assert manifest["synthetic"] is True
    assert manifest["seed"] == 20261014
    assert manifest["ruleset_id"] == "GBZ188-2025"
    assert manifest["record_count"] == manifest["clean_count"] + (
        manifest["record_count"] - manifest["clean_count"]
    )
    assert manifest["coverage_matrix"], "必须登记算例覆盖矩阵"
    assert manifest["unreachable_cases"], "必须如实声明不可达算例"


# ---------------- M1-4：真值与引擎对账（独立实现路径）----------------


def test_every_truth_record_reconciles_with_engine():
    """逐件对账：引擎结论与植入真值必须一致（M2 前的真值库自洽性守门）。

    真值由 `tools/gen_synthetic.py` 的**独立参考实现**算出（不调引擎），
    故本测试同时是"引擎与真值同源修正"的判别依据（plan/05 §2.4）。
    """
    context = build_context()
    total = 0
    for name, obj in _records():
        expect = dict(obj["expect"])
        record_obj = {k: v for k, v in obj.items() if k not in ("expect", "expect_case")}
        record = build_record(record_obj)
        result = compute_coverage(record, context)
        outcome = compare_expected(result, expect)
        assert outcome["ok"], (name, outcome)
        total += 1
    assert total >= 60, "真值库件数过少（应覆盖算例矩阵全部行）"


def test_truth_records_use_only_synthetic_identities():
    """命名白名单：虚构姓名代号 + 测试号段（plan/05 §2.2，禁真实劳动者信息）。"""
    for name, obj in _records():
        assert obj["employee_name"].startswith("示例人员 A-"), name
        assert obj["employee_id"].startswith("90000000"), name
        assert obj["employee_id"].endswith("SYN"), name


def test_truth_records_are_deterministic_across_two_generations():
    """同 seed 两次生成的字节必须一致（比 --check 更强：跨进程两次现算）。"""
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "gen_synthetic_under_test", os.path.join(repo_root(), "tools", "gen_synthetic.py")
    )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    first = module.build_outputs()
    second = module.build_outputs()
    assert sorted(first) == sorted(second)
    for key in sorted(first):
        assert first[key] == second[key], key


# ---------------- M1-5：误报对照集显式声明 ----------------


def test_clean_declarations_are_explicit_and_nonempty():
    """误报对照集必须由真值库**显式声明**（should_be_clean），且非空。"""
    clean = [
        (name, obj) for name, obj in _records() if is_clean_expect(obj.get("expect") or {})
    ]
    assert len(clean) >= 10, "应零命中的干净档案过少"
    for _name, obj in clean:
        assert obj["expect"]["verdict"] == "compliant"
        assert obj["expect"]["missing_items"] == []
        assert obj["expect"]["period_verdict"] in ("compliant", "due", "no_baseline",
                                                  "not_applicable", "input_required")


def test_clean_declared_records_actually_produce_no_findings():
    """零命中实测：声明为干净者，引擎不得报缺项/不得判不符合。"""
    context = build_context()
    for name, obj in _records():
        expect = obj.get("expect") or {}
        if not is_clean_expect(expect):
            continue
        record_obj = {k: v for k, v in obj.items() if k not in ("expect", "expect_case")}
        result = compute_coverage(build_record(record_obj), context)
        assert result.verdict == "compliant", (name, result.verdict, result.missing_items)
        assert result.missing_items == [], (name, result.missing_items)
        assert result.period_verdict != "overdue", name


def test_alias_written_but_clean_record_degrades_to_warning_not_failure():
    """别名写法件的显式声明：应零 fail、允许 warning（决策 D-17）。"""
    found = None
    for name, obj in _records():
        expect = obj.get("expect") or {}
        if expect.get("also_expect") and any(
            e.get("kind") == "warning" for e in expect["also_expect"]
        ):
            found = (name, obj)
            break
    assert found is not None, "真值库应含一件『别名写法 → 降级 warning』档案"
    name, obj = found
    record_obj = {k: v for k, v in obj.items() if k not in ("expect", "expect_case")}
    result = compute_coverage(build_record(record_obj), build_context())
    assert result.verdict == "compliant", name
    assert result.unmapped_items, "别名写法应记入 unmapped"
    assert not result.is_noncompliant, name
    assert any(f["kind"] == "warning" for f in result.findings), name


# ---------------- M1-7：门控作用域在**真实数据**上验证 ----------------


def test_real_ruleset_gate_blocks_referenced_pending_only():
    """plan/check（full 深度）只拦**引用到的** pending 条目。

    真实混态：第 5 章苯已核对（放行）；第 8 章布鲁氏菌明细 pending（拦截）；
    未引用的第 8/9 章 pending 条目不阻断他因素。
    """
    ruleset = load_ruleset("GBZ188-2025")
    # 引用已核对因素 → 放行
    eff = effective_ruleset(ruleset, "plan", required_factor_ids=["GBZ188-5.19"])
    assert eff.used_factor_codes == ["GBZ188-5.19"]
    # 引用未核对明细因素 → 拦截
    with pytest.raises(GateBlocked) as exc:
        effective_ruleset(ruleset, "plan", required_factor_ids=["GBZ188-8.1"])
    assert exc.value.exit_code == 2
    assert any("8.1" in b for b in exc.value.blocked)


def test_real_ruleset_compare_passes_despite_pending_details():
    """compare/bench（minimal 深度）在项目明细 pending 时**仍放行**（决策 D-12）。"""
    ruleset = load_ruleset("GBZ188-2025")
    eff = effective_ruleset(ruleset, "compare", required_factor_ids=["GBZ188-8.1"])
    assert eff.ruleset_id == "GBZ188-2025"
    # 整包（不指定因素）也应放行
    eff_all = effective_ruleset(ruleset, "bench")
    assert eff_all.ruleset_id == "GBZ188-2025"


def test_real_ruleset_period_tiering_does_not_block_verified_items():
    """M1 实测发现 A：周期按分级分档（input_required）**不得**阻断已核对的因素。

    噪声（7.1）的必检项已核对，仅周期分档 → plan 必须放行，且以待输入形式呈现周期。
    修前：整条因素被 MissingInputError 拦死 → FR-B4 在主要因素上不可达。
    """
    context = build_context()
    profile = build_position(
        {
            "position_id": "POS-NOISE",
            "exam_date": "2026-09-20",
            "factors": [{"factor_code": "GBZ188-7.1"}],
        }
    )
    result = compute_plan(profile, context)  # 编排层：含门控放行 + 待输入处置
    factor_plan = result.factors[0]
    assert factor_plan.applicability.state == "applicable"
    assert factor_plan.exams["periodic"].required_items, "必检项应已推导"
    # 周期待输入被显式索取（不静默），但不阻塞
    deferred = [m for m in result.missing_inputs if not m.get("blocking", True)]
    assert deferred, "周期分档应作为待输入项被显式列出"


def test_real_ruleset_period_verdict_reports_input_required_not_overdue():
    """周期分档时判定为 input_required（**不误报超期**）。"""
    context = build_context()
    record = build_record(
        {
            "record_id": "SYN-TRUTH-006",
            "employee_id": "90000000006SYN",
            "factor_code": "GBZ188-7.1",
            "exam_date": "2026-09-20",
            "exam_type": "periodic",
            "items": ["血常规", "尿常规", "肝功能", "心电图", "纯音听阈测试"],
            "last_exam_date": "2025-09-20",
        }
    )
    result = compute_coverage(record, context)
    assert result.period_verdict == "input_required"
    assert result.verdict == "compliant"


def test_real_ruleset_identity_only_factor_still_reports_unknown_not_compliant():
    """未核对明细的因素：档案级判定不得降级成 compliant。"""
    ruleset = load_ruleset("GBZ188-2025")
    # full 深度拦截 → 调用方得到 GateBlocked（不是"合规"）
    with pytest.raises(GateBlocked):
        effective_ruleset(ruleset, "check", required_factor_ids=["GBZ188-9.1"])


# ---------------- M1-1：官方原文快照与依据索引 ----------------


def test_official_snapshots_are_present_and_hanzi_count_intact():
    """官方快照入库且汉字数零丢失（M1-1）。

    75,555 汉字是 M0 期实测的解析统计；本测试把它锁成守门值——
    解析器或快照任一变动都会在此暴露。
    """
    raw_dir = os.path.join(data_dir(), "knowledge", "raw")
    pdf = os.path.join(raw_dir, "GBZ188-2025.pdf")
    text = os.path.join(raw_dir, "GBZ188-2025.layout.txt")
    assert os.path.isfile(pdf), "官方 PDF 快照未入库"
    assert os.path.isfile(text), "解析文本快照未入库"
    assert os.path.getsize(pdf) == 1553783, "PDF 快照字节数变化（快照应冻结）"
    with open(text, "r", encoding="utf-8") as fh:
        content = fh.read()
    hanzi = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff")
    assert hanzi == 75555, "汉字数偏离（解析丢字）"


def test_official_snapshots_are_marked_no_normalize_in_gitattributes():
    """`.gitattributes` 必须对 `data/knowledge/raw/**` 标 `-text`（防行尾归一化改写
    快照字节 → 克隆后 sha256 失配，决策 D-26）。"""
    root = repo_root()
    with open(os.path.join(root, ".gitattributes"), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "data/knowledge/raw/** -text" in text


def test_clauses_index_covers_all_sections_and_records_snapshot_fingerprint():
    """依据索引（M1-2c）：每个节次都挂标准号 + 节号 + URL + 抓取日期 + 快照 sha256。"""
    clauses = load_path(os.path.join(data_dir(), "knowledge", "clauses.json"))
    assert clauses["clauses"], "依据索引不得为空"
    assert len(clauses["clauses"]) == 97, "应覆盖第 5–9 章全部 97 个节次"
    assert clauses["pending_verifications"], "待核对项必须登记（未核对不得静默）"
    snapshot_sha = clauses["snapshots"][1]["sha256"]
    for entry in clauses["clauses"]:
        assert entry["doc_code"] == "GBZ 188—2025"
        assert entry["url"].startswith("https://www.gov.cn/")
        assert entry["fetched"] == "2026-10-14"
        assert entry["snapshot_sha256"] == snapshot_sha
    # 明细核对状态如实标注
    verified = [c for c in clauses["clauses"] if c["detail_verified"]]
    identity_only = [c for c in clauses["clauses"] if not c["detail_verified"]]
    assert len(verified) == 82, "第 5–7 章应为 82 个明细已核对节次"
    assert len(identity_only) == 15, "第 8–9 章应为 15 个仅身份节次"


def test_clauses_index_foreword_deltas_are_verbatim_in_snapshot():
    """前言差异条目必须逐字出自官方快照（C8 核对清单）。"""
    clauses = load_path(os.path.join(data_dir(), "knowledge", "clauses.json"))
    with open(
        os.path.join(data_dir(), "knowledge", "raw", "GBZ188-2025.layout.txt"),
        "r", encoding="utf-8",
    ) as fh:
        flat = "".join(fh.read().split())
    assert clauses["foreword_deltas"], "前言差异条目不得为空"
    for delta in clauses["foreword_deltas"]:
        assert "".join(delta["text"].split()) in flat, delta["text"][:40]
