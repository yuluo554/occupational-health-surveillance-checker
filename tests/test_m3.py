"""M3：批量、对账、报告与证据链。

对应 DoD：M3-1 … M3-9（plan/05 §四）。
  M3-1/2  批量扫描失败隔离：全原因码逐码有件、失败件 ≠ 违规、check/scan 同分派点
  M3-3    跨轮对账三主集 + 两辅助集（补齐必须检得出；--baseline 已接线）
  M3-4    群体统计可复算（sum(明细) == 统计 + detail_sha256）
  M3-5/6/7 报告三性质：单一渲染源两格式对等、字节可复现、无外链
  M3-8    证据链含报告自指纹（批量 scan 通路）
  M3-9    报告头 / §9 参数来源 / §11 免责声明 / "未启用"显式（批量通路复查）
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pytest

from helpers import make_factor, make_record, make_temp_data_dir, write_json

from ohscheck.cli import main
from ohscheck.engine.export import export_report
from ohscheck.engine.pipeline import (
    build_context,
    build_record,
    build_report_model,
    compare_rounds_model,
    compute_coverage,
    run_scan,
)
from ohscheck.engine.scan import DEFAULT_MAX_BYTES, ScanResult, scan_directory
from ohscheck.loaders import load_path
from ohscheck.model import CoverageResult
from ohscheck.report.markdown import render_markdown
from ohscheck.report.sections import report_sections
from ohscheck.report.xlsx import render_xlsx_bytes, render_xlsx_table


@pytest.fixture()
def env(tmp_path):
    """两岗位、必检项 T_ITEM_1/T_ITEM_2 的合成数据目录；另含一个 pending 因素
    （gate_blocked 原因码的触发件——引用到未核对条目必须被门控拦截，D-12）。"""
    factors = [
        make_factor(code="T_FACTOR", fid="5.1.0", months=12,
                    required=("T_ITEM_1", "T_ITEM_2")),
        make_factor(code="T_PENDING", fid="8.1.0", months=12,
                    required=("P1",), factor_status="pending",
                    exam_status="pending", period_status="pending"),
    ]
    root = tmp_path / "data"
    root.mkdir()
    data_dir = make_temp_data_dir(str(root), factors=factors)
    return {"data_dir": data_dir, "tmp_path": tmp_path}


def _scan_dir(tmp_path, name, records, extra_files=None):
    """物化一个档案目录；extra_files = {文件名: bytes}（坏件夹具）。"""
    directory = tmp_path / name
    directory.mkdir(exist_ok=True)
    for i, rec in enumerate(records):
        write_json(str(directory / ("rec-%02d.json" % i)), rec)
    for fname, blob in (extra_files or {}).items():
        (directory / fname).write_bytes(blob)
    return str(directory)


def _run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


# ---------------- M3-1：全原因码逐码有件（失败隔离） ----------------


def _reason_code_fixtures(tmp_path):
    """构造各"未判定"原因码的触发件（目录内文件名 → 原因码）。

      bad_json            坏 JSON
      schema_invalid      合法 JSON 但缺必填字段
      unknown_factor      档案引用规则集不存在的因素
      unknown_exam_type   时点不识别
      gate_blocked        引用到 pending 条目（合成包 T_PENDING，门控拦截）
      missing_input       适用性待输入（另测，见 test_missing_input_reason_is_isolated）
      container_too_large 超过单件上限（安全阀）
      read_error          引擎层注入（不依赖平台权限位）
    """
    rec = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    files = {
        "f-badjson.json": b"{not json",
        "f-schema.json": json.dumps({"record_id": "X"}).encode("utf-8"),
        "f-unknown-factor.json": json.dumps(
            make_record(factor_code="NO_SUCH_FACTOR", items=(), exam_type="pre_placement")
        ).encode("utf-8"),
        "f-unknown-exam.json": json.dumps(
            dict(rec, exam_type="mid_term")
        ).encode("utf-8"),
        "f-gate.json": json.dumps(
            make_record(factor_code="T_PENDING", items=(), exam_type="pre_placement")
        ).encode("utf-8"),
    }
    return rec, files


def test_every_reason_code_has_a_fixture_and_is_isolated(env):
    """M3-1：原因码逐码有件，全部隔离为 failed（不进 items），失败不中断整批。"""
    rec, files = _reason_code_fixtures(env["tmp_path"])
    scan_dir = _scan_dir(env["tmp_path"], "records", [rec], extra_files=files)

    context = build_context(env["data_dir"])
    result = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    reasons = {f.reason for f in result.failed}
    for expected in (
        "bad_json",
        "schema_invalid",
        "unknown_factor",
        "unknown_exam_type",
        "gate_blocked",
    ):
        assert expected in reasons, (expected, sorted(reasons))
    # 失败件不混入判定明细；好件正常判定（失败隔离）
    assert len(result.items) == 1
    assert result.items[0].verdict == "compliant"
    assert all(f.reason not in ("missing_input", "read_error", "container_too_large")
               for f in result.failed)


def test_read_error_reason_injected_at_engine_level(env):
    """M3-1：read_error 由引擎层注入验证（不依赖平台权限位）。"""
    rec, files = _reason_code_fixtures(env["tmp_path"])
    scan_dir = _scan_dir(env["tmp_path"], "records", [rec], extra_files=files)
    context = build_context(env["data_dir"])

    from ohscheck.engine import scan as scan_mod

    original = scan_mod.os.path.getsize

    def flaky(path):
        if "f-badjson" in str(path):
            raise OSError("模拟读盘失败")
        return original(path)

    scan_mod.os.path.getsize = flaky
    try:
        result = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    finally:
        scan_mod.os.path.getsize = original
    assert "read_error" in {f.reason for f in result.failed}


def _plan_provider(context, record):
    from ohscheck.engine.pipeline import _plan_for_record

    return _plan_for_record(record, context)


def test_container_too_large_via_engine_safety_valve(env):
    """M3-1：超大输入走安全阀（container_too_large），不整体读入。"""
    scan_dir = _scan_dir(
        env["tmp_path"], "records", [],
        extra_files={"big.json": b"[" + b"0" * 4096 + b"]"},
    )
    context = build_context(env["data_dir"])
    result = scan_directory(
        scan_dir, lambda c, d, r: _plan_provider(context, r), max_bytes=16
    )
    assert "container_too_large" in {f.reason for f in result.failed}


def test_missing_input_reason_is_isolated(tmp_path):
    """M3-1：适用性待输入（input_required）→ missing_input 原因码隔离。"""
    factor = make_factor(code="T_FACTOR", required=("A1",))
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = "需按具体情况确定（规则包不承载）"
    root = tmp_path / "data"
    root.mkdir()
    data_dir = make_temp_data_dir(str(root), factors=[factor])
    scan_dir = _scan_dir(
        tmp_path, "records",
        [make_record(items=("A1",), exam_type="pre_placement")],
    )
    context = build_context(data_dir)
    result = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    assert "missing_input" in {f.reason for f in result.failed}
    assert result.items == []


def test_reason_code_counted_individually(env):
    """M3-1：失败件原因码**单列**——逐码计数可从 ScanResult 复算。"""
    _rec, files = _reason_code_fixtures(env["tmp_path"])
    scan_dir = _scan_dir(env["tmp_path"], "records", [], extra_files=files)
    context = build_context(env["data_dir"])
    result = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    counts = {}
    for f in result.failed:
        counts[f.reason] = counts.get(f.reason, 0) + 1
    assert counts.get("bad_json") == 1
    assert counts.get("schema_invalid") == 1
    assert counts.get("unknown_factor") == 1
    assert counts.get("unknown_exam_type") == 1
    assert counts.get("gate_blocked") == 1
    # 逐码计数之和 == failed 总数（单列不重复不遗漏）
    assert sum(counts.values()) == len(result.failed)


# ---------------- M3-1/M3-2：check 与 scan 同分派点 + 失败件 ≠ 违规 ----------------


def test_check_and_scan_agree_field_by_field(env):
    """M3-1：同一档案 check（单件）与 scan（批量）结论**逐字段相同**（决策 D-32）。"""
    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    rec_path = str(env["tmp_path"] / "single.json")
    write_json(rec_path, rec)
    scan_dir = _scan_dir(env["tmp_path"], "records", [rec])

    context = build_context(env["data_dir"])

    # check 通路
    single = build_record(load_path(rec_path))
    via_check = compute_coverage(single, context)

    # scan 通路（同目录单件）
    via_scan = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))

    assert len(via_scan.items) == 1
    a, b = via_check.as_dict(), via_scan.items[0].as_dict()
    for key in sorted(set(a) | set(b)):
        assert a.get(key) == b.get(key), key


def test_scan_cli_exit_code_ignores_failed_items(env):
    """M3-2：坏 JSON + 超限件混入 → 退出码仍由**判定结论**决定（D-21）。"""
    rec = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    scan_dir = _scan_dir(
        env["tmp_path"], "records", [rec],
        extra_files={"f-bad.json": b"{oops"},
    )
    code, out, _err = _run_cli([
        "scan", scan_dir, "--data-dir", env["data_dir"], "--json",
    ])
    # 判定件全部合规 → 退出码 0；坏件不改变退出码
    assert code == 0, out
    payload = json.loads(out)
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["reason"] in ("bad_json", "schema_invalid")
    assert payload["stats"]["total"] == 1


def test_scan_cli_exit_1_only_on_judged_noncompliant(env):
    """M3-2：退出码 1 只来自**已判定**的不符合，失败件不贡献。"""
    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")  # 缺 T_ITEM_2
    scan_dir = _scan_dir(
        env["tmp_path"], "records", [rec],
        extra_files={"f-bad.json": b"{oops"},
    )
    code, out, _err = _run_cli([
        "scan", scan_dir, "--data-dir", env["data_dir"], "--json",
    ])
    assert code == 1, out
    payload = json.loads(out)
    assert payload["stats"]["total"] == 1
    assert len(payload["failed"]) == 1


# ---------------- M3-3：跨轮对账 ----------------


def _coverage_scan(records):
    """把 CoverageResult 列表装进 ScanResult（对账测试的轻量装配）。"""
    scan = ScanResult()
    scan.items = list(records)
    scan.compute_stats()
    return scan


def _cov(record_id, employee_id, factor_code, missing, period_verdict=""):
    return CoverageResult(
        record_id=record_id,
        employee_id=employee_id,
        factor_code=factor_code,
        exam_type="periodic",
        verdict="partial" if missing else "compliant",
        missing_items=list(missing),
        period_verdict=period_verdict,
    )


def test_reconcile_resolved_detected_when_item_supplied(env):
    """M3-3：**两轮之间补上一项 → resolved 检出**（不得只写不做）。

    配对主键 = employee_id + 缺项坐标（D-20）：同一个人同一坐标，
    上轮缺、本轮不缺 → resolved；补齐必然内容变了——正因主键是身份键
    而非内容指纹，才配得上对。
    """
    emp = "SYN-E2E-001"
    baseline = _coverage_scan([
        _cov("R1", emp, "T_FACTOR", ["T_ITEM_1", "T_ITEM_2"]),
    ])
    current = _coverage_scan([
        _cov("R1", emp, "T_FACTOR", ["T_ITEM_2"]),  # 已补 T_ITEM_1
    ])
    rec = compare_rounds_model(current, baseline)
    targets = {item["target"] for item in rec.resolved}
    assert any("T_ITEM_1" in t for t in targets), rec.resolved
    # 其余仍是持续缺失
    persistent_targets = {item["target"] for item in rec.persistent}
    assert any("T_ITEM_2" in t for t in persistent_targets)
    assert rec.new_missing == []
    # 内容变化另立标记，不退化成"新增 + 移除"（D-20 纪律②）
    assert {"employee_id": emp} in rec.content_changed
    assert rec.aux["new_records"] == []
    assert rec.aux["gone_records"] == []


def test_reconcile_new_missing_and_persistent(env):
    """M3-3：新增缺项 / 持续缺失 / 件级增删（三主集 + 两辅助集）。"""
    baseline = _coverage_scan([
        _cov("R1", "E-1", "T_FACTOR", ["T_ITEM_2"]),
    ])
    current = _coverage_scan([
        _cov("R1", "E-1", "T_FACTOR", ["T_ITEM_1", "T_ITEM_2"]),  # 新缺 T_ITEM_1
        _cov("R2", "E-2", "T_FACTOR", ["T_ITEM_1"]),               # 新增档案
    ])
    rec = compare_rounds_model(current, baseline)
    assert any("T_ITEM_1" in item["target"] for item in rec.new_missing)
    assert any("T_ITEM_2" in item["target"] for item in rec.persistent)
    assert rec.resolved == []
    assert rec.aux["new_records"] == ["E-2"]
    assert rec.aux["gone_records"] == []
    assert {"employee_id": "E-1"} in rec.content_changed


def test_reconcile_gone_records_and_unchanged(env):
    """M3-3：消失档案 + 完全无变化（对账零命中不误报）。"""
    baseline = _coverage_scan([
        _cov("R1", "E-1", "T_FACTOR", ["T_ITEM_1"]),
        _cov("R2", "E-2", "T_FACTOR", []),
    ])
    current = _coverage_scan([
        _cov("R1", "E-1", "T_FACTOR", ["T_ITEM_1"]),  # 未变
    ])
    rec = compare_rounds_model(current, baseline)
    assert rec.new_missing == [] and rec.resolved == [] and rec.persistent == [
        {"employee_id": "E-1", "target": "T_FACTOR/periodic/T_ITEM_1"}
    ]
    assert rec.content_changed == []
    assert rec.aux["new_records"] == []
    assert rec.aux["gone_records"] == ["E-2"]


def test_reconcile_truth_driven_full_round(tmp_path):
    """M3-3：真值驱动端到端——真实规则包扫描两轮目录（CLI --baseline 接线）。"""
    context = build_context()  # 生产规则包
    base = load_path(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "truth", "records", "SYN-TRUTH-008.json",
    ))
    rec_obj = {k: v for k, v in base.items() if k not in ("expect", "expect_case")}
    round1 = tmp_path / "round1"
    round1.mkdir()
    write_json(str(round1 / "r.json"), rec_obj)
    # 第二轮：补上缺的「肝功能」
    fixed = dict(rec_obj)
    fixed["items"] = list(rec_obj["items"]) + ["肝功能"]
    round2 = tmp_path / "round2"
    round2.mkdir()
    write_json(str(round2 / "r.json"), fixed)

    r1 = run_scan(str(round1), context)
    r2 = run_scan(str(round2), context)
    rec = compare_rounds_model(r2, r1)
    assert any("肝功能" in item["target"] for item in rec.resolved), rec.as_dict()
    assert rec.new_missing == []


def test_reconcile_via_cli_baseline_flag(env):
    """M3-3：CLI 端到端——`report --baseline` 产出 §7 对账章节（不再恒"未启用"）。"""
    rec1 = make_record(items=("T_ITEM_1",), exam_type="pre_placement")  # 缺 T_ITEM_2
    rec2 = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    baseline_dir = _scan_dir(env["tmp_path"], "round1", [rec1])
    current_dir = _scan_dir(env["tmp_path"], "round2", [rec2])
    out_dir = env["tmp_path"] / "out"

    code, out, err = _run_cli([
        "report", str(out_dir),
        "--directory", current_dir, "--baseline", baseline_dir,
        "--data-dir", env["data_dir"],
        "--generated-at", "2026-10-14T00:00:00", "--json",
    ])
    assert code == 0, out + err
    md_path = os.path.join(str(out_dir), "report.md")
    with open(md_path, "rb") as fh:
        md = fh.read().decode("utf-8")
    assert "跨轮对账" in md
    assert "已补齐" in md
    assert "本次导出未启用跨轮对账" not in md
    evidence = load_path(os.path.join(str(out_dir), "evidence.json"))
    names = {item["path"] for item in evidence["inputs"]}
    # 目录输入逐文件挂指纹（M3-8 的输入侧）：round2 的档案必须在列
    assert any("round2" in p for p in names), names
    assert any("round1" in p for p in names), names


def test_reconcile_via_scan_cli_baseline_flag(env):
    """M3-3：`scan --baseline --out` 同样接线对账。"""
    rec1 = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    rec2 = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    baseline_dir = _scan_dir(env["tmp_path"], "round1", [rec1])
    current_dir = _scan_dir(env["tmp_path"], "round2", [rec2])
    out_dir = env["tmp_path"] / "out"

    code, out, err = _run_cli([
        "scan", current_dir, "--baseline", baseline_dir,
        "--out", str(out_dir), "--data-dir", env["data_dir"],
        "--generated-at", "2026-10-14T00:00:00", "--json",
    ])
    assert code == 0, out + err
    payload = json.loads(out)
    assert "baseline" in payload
    md_path = os.path.join(str(out_dir), "report.md")
    with open(md_path, "rb") as fh:
        md = fh.read().decode("utf-8")
    assert "已补齐" in md


# ---------------- M3-4：群体统计逐项可复算 ----------------


def test_stats_recomputed_from_details_match(env):
    """M3-4：sum(明细) == 统计（按因素与按岗位两维，硬断言）。"""
    records = [
        make_record(record_id="A", employee_id="E-1", position_id="POS-A",
                    items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement"),
        make_record(record_id="B", employee_id="E-2", position_id="POS-A",
                    items=("T_ITEM_1",), exam_type="pre_placement"),          # partial
        make_record(record_id="C", employee_id="E-3", position_id="POS-B",
                    items=(), exam_type="pre_placement"),                     # non_compliant
    ]
    scan_dir = _scan_dir(env["tmp_path"], "records", records)
    context = build_context(env["data_dir"])
    combined = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    assert len(combined.items) == 3

    stats = combined.stats
    # 独立复算（从 items 明细重推，不消费 compute_stats 的内部状态）。
    # 桶口径与引擎一致：by_factor 桶的 position_id 恒为空串（因素维不带岗位）、
    # by_position 桶的 factor_code 恒为空串（岗位维不带因素）。
    for dim in ("by_factor", "by_position"):
        key = "factor_code" if dim == "by_factor" else "position_id"
        recomputed = {}
        for rec in combined.items:
            b = recomputed.setdefault(getattr(rec, key), {
                "factor_code": rec.factor_code if dim == "by_factor" else "",
                "position_id": rec.position_id if dim == "by_position" else "",
                "examined": 0, "compliant": 0, "noncompliant": 0,
                "not_applicable": 0, "unknown": 0,
            })
            b["examined"] += 1
            v = rec.verdict
            if v in ("partial", "non_compliant"):
                b["noncompliant"] += 1
            elif v == "compliant":
                b["compliant"] += 1
            elif v == "not_applicable":
                b["not_applicable"] += 1
            else:
                b["unknown"] += 1
        reported = {b[key]: b for b in stats[dim]}
        assert reported == recomputed, (dim, reported, recomputed)
    assert stats["total"] == len(combined.items)
    assert stats["failed"] == len(combined.failed)


def test_stats_detail_sha256_changes_with_details(env):
    """M3-4：明细变 → detail_sha256 必变（统计绑定明细，防两头漂）。"""
    rec_ok = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    scan_a = _scan_dir(env["tmp_path"], "a", [rec_ok])
    rec_missing = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    scan_b = _scan_dir(env["tmp_path"], "b", [rec_missing])
    context = build_context(env["data_dir"])
    sha_a = scan_directory(scan_a, lambda c, d, r: _plan_provider(context, r)).stats["detail_sha256"]
    sha_b = scan_directory(scan_b, lambda c, d, r: _plan_provider(context, r)).stats["detail_sha256"]
    assert sha_a != sha_b


# ---------------- M3-5：单一渲染源（含 §4/§5/§6/§7 两格式对等） ----------------


def _scan_model(env, records, reconcile=None):
    context = build_context(env["data_dir"])
    scan_dir = _scan_dir(env["tmp_path"], "records", records)
    scan = scan_directory(scan_dir, lambda c, d, r: _plan_provider(context, r))
    return build_report_model(
        scan_result=scan, reconcile_result=reconcile, context=context,
        ruleset_id="SYN-TEST", generated_at="2026-10-14T00:00:00",
    )


def test_both_formats_carry_every_section_and_table(env):
    """M3-5：两格式逐项对等——每个章节标题与每张表标题在 MD 与 XLSX 行里都出现。"""
    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    sections = report_sections(model)
    md = render_markdown(model, sections)
    flat = ["\t".join(r) for r in render_xlsx_table(model, sections)]
    for section in sections:
        assert section.title in md, section.title
        assert any(section.title in row for row in flat), section.title
        for table in section.tables:
            assert table.title in md, table.title
            assert any(table.title in row for row in flat), table.title


def test_both_formats_carry_batch_tables_verbatim(env):
    """M3-5：M2 新增表（§4 可达性 / §5 待输入 / §6 岗位维 / §7 对账）两格式同步。"""
    rec_missing = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    baseline = _coverage_scan([_cov("R1", "E-1", "T_FACTOR", ["T_ITEM_2"])])
    model = _scan_model(env, [rec_missing], reconcile=compare_rounds_model(
        _coverage_scan([_cov("R1", "E-1", "T_FACTOR", ["T_ITEM_1"])]), baseline))
    # 注入一份"周期待输入"判定（机制层；真实数据侧由 test_m2 真值件锁定）
    model.scan_result.items.append(CoverageResult(
        record_id="R-PEND", employee_id="E-PEND", position_id="POS-PEND",
        factor_code="GBZ188-7.1", exam_type="periodic",
        verdict="compliant", period_verdict="input_required",
    ))
    sections = report_sections(model)
    md = render_markdown(model, sections)
    flat = ["\t".join(r) for r in render_xlsx_table(model, sections)]

    def in_both(text):
        assert text in md, text
        assert any(text in row for row in flat), text

    in_both("四态可达性")            # §4（真实包上 not_applicable 不可达的声明）
    in_both("周期待输入")            # §5 分档待输入单列
    in_both("按岗位汇总")            # §6 两维汇总的岗位维
    in_both("跨轮对账")              # §7
    in_both("已补齐")                # 三主集
    in_both("内容变化")              # content_changed 行
    in_both("按危害因素汇总")        # §6 因素维（原有）
    in_both("失败件清单")            # §10
    # 每张表的表头行也须两格式都有
    for table in [t for s in sections for t in s.tables]:
        header = "| " + " | ".join(table.headers) + " |"
        assert header in md, header


# ---------------- M3-6/M3-7：字节可复现 + 无外链（批量通路实测） ----------------


def test_batch_report_bytes_reproducible_two_runs(env):
    """M3-6：scan 通路的报告**两次导出 sha256 实测一致**（不得只写不做）。"""
    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    out1 = env["tmp_path"] / "o1"
    out2 = env["tmp_path"] / "o2"
    r1 = export_report(model, str(out1))
    r2 = export_report(model, str(out2))
    assert r1["sha256"] == r2["sha256"]
    for name, digest in r1["sha256"].items():
        with open(os.path.join(str(out1), name), "rb") as fh:
            first = fh.read()
        with open(os.path.join(str(out2), name), "rb") as fh:
            second = fh.read()
        assert first == second, name


def test_batch_report_no_external_links(env):
    """M3-7：scan 通路报告同样无外链（MD 无 ]( ；XLSX 无外部关系/hyperlink）。"""
    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    md = render_markdown(model)
    assert "](" not in md
    xlsx = render_xlsx_bytes(model)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as zf:
        for name in zf.namelist():
            content = zf.read(name).decode("utf-8", "replace")
            assert 'TargetMode="External"' not in content, name
            assert "w:hyperlink" not in content, name


# ---------------- M3-8：证据链（批量 scan 通路含报告自指纹） ----------------


def test_batch_scan_evidence_covers_self_fingerprint(env):
    """M3-8：scan --out 的证据链含报告**自身** sha256；篡改即检出。"""
    from ohscheck.report.evidence import verify_evidence

    rec = make_record(items=("T_ITEM_1",), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    out = env["tmp_path"] / "out"
    info = export_report(model, str(out))

    payload = load_path(info["evidence"])
    names = {item["path"] for item in payload["outputs"]}
    assert {"report.md", "report.xlsx"}.issubset(names)
    assert verify_evidence(info["evidence"])["ok"] is True

    # 篡改 XLSX → 证据链检出（MD 通路在 M0 已测；这里补批量通路的 XLSX 侧）
    with open(info["xlsx"], "ab") as fh:
        fh.write(b"tampered")
    result = verify_evidence(info["evidence"])
    assert result["ok"] is False
    assert "report.xlsx" in result["mismatched"]


# ---------------- M3-9：报告头 / §9 / §11 / "未启用"显式（批量通路） ----------------


def test_batch_report_header_parameter_disclaimer(env):
    """M3-9：报告头规则包坐标 + §9 参数来源块 + §11 免责声明（scan 通路）。"""
    rec = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    md = render_markdown(model)
    assert "规则包坐标" in md
    assert "参数来源块" in md
    assert "不构成医学意见" in md
    assert "免责声明" in md
    # §9 参数来源带 sha256 指纹（make_temp_data_dir 填真实 sha）
    assert all(s.get("sha256") for s in model.parameter_sources)


def test_period_input_required_table_explicit_when_no_periodic_records(env):
    """M3-9：批量通路上若无在岗期间档案 → §5 显式写"未启用/无周期判定结果"。"""
    rec = make_record(items=("T_ITEM_1", "T_ITEM_2"), exam_type="pre_placement")
    model = _scan_model(env, [rec])
    s5 = [s for s in report_sections(model) if s.number == "5"][0]
    assert s5.paragraphs, "§5 不得为空段（没查 ≠ 查了没问题）"
    assert "未启用" in s5.paragraphs[0] or "无周期判定结果" in s5.paragraphs[0]
    md = render_markdown(model)
    assert "无周期判定结果" in md
    # XLSX 侧同步（两格式对等）
    flat = ["\t".join(r) for r in render_xlsx_table(model)]
    assert any("无周期判定结果" in row for row in flat)


def test_period_input_required_table_lists_pending_records():
    """M3-9：在岗期间分档因素 → §5"周期待输入"表逐件列出（不与合规同表）。

    机制层用装配结果验证（真实数据侧由 test_m2.test_report_period_section_separates_
    input_required 以真值件 SYN-TRUTH-006 锁定）。
    """
    context = build_context()  # 生产规则包（供 §4 可达性等）
    scan = ScanResult()
    scan.items = [
        CoverageResult(
            record_id="R-PEND-1",
            employee_id="E-PEND",
            position_id="POS-PEND",
            factor_code="GBZ188-7.1",
            exam_type="periodic",
            verdict="compliant",
            period_verdict="input_required",
        ),
        CoverageResult(
            record_id="R-OK-1",
            employee_id="E-OK",
            position_id="POS-PEND",
            factor_code="GBZ188-5.19",
            exam_type="periodic",
            verdict="compliant",
            period_verdict="compliant",
        ),
    ]
    model = build_report_model(
        scan_result=scan, context=context, ruleset_id="GBZ188-2025",
        generated_at="2026-10-14T00:00:00",
    )
    s5 = [s for s in report_sections(model) if s.number == "5"][0]
    titles = [t.title for t in s5.tables]
    assert "周期待输入（不判合规，亦不判超期）" in titles
    md = render_markdown(model)
    assert "待输入（周期按分级/接触水平分档）" in md
    # 合规件在"周期判定"表、待输入件在"周期待输入"表——两表分列（D-65）
    pend_table = [t for t in s5.tables if "周期待输入" in t.title][0]
    main_table = [t for t in s5.tables if t.title == "周期判定"][0]
    assert any("R-PEND-1" in str(r) for r in pend_table.rows)
    assert all("R-PEND-1" not in str(r) for r in main_table.rows)
