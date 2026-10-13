"""报告导出：单一渲染源、字节可复现、无外链、证据链、显式"未启用"。

对应 DoD：M3-5/6/7/8/9（骨架期先把机制锁死，M3 数据到位后即生效）。
"""

from __future__ import annotations

import os
import zipfile

import pytest

from helpers import make_factor, make_record, make_temp_data_dir, write_json

from ohscheck.engine.export import export_report
from ohscheck.engine.pipeline import (
    build_context,
    build_record,
    build_report_model,
    compute_coverage,
)
from ohscheck.loaders import load_path
from ohscheck.report.markdown import render_markdown
from ohscheck.report.sections import report_sections
from ohscheck.report.xlsx import render_xlsx_bytes, render_xlsx_table


@pytest.fixture()
def env(tmp_path):
    factors = [make_factor(code="T_FACTOR", fid="5.1.0", months=12, required=("A1", "A2"))]
    root = tmp_path / "data"
    root.mkdir()
    data_dir = make_temp_data_dir(str(root), factors=factors)
    return {"data_dir": data_dir, "tmp_path": tmp_path}


def _coverage(env, items=("A1", "A2"), exam_type="pre_placement"):
    context = build_context(env["data_dir"])
    rec_path = str(env["tmp_path"] / "rec.json")
    write_json(rec_path, make_record(items=items, exam_type=exam_type))
    record = build_record(load_path(rec_path))
    return context, [compute_coverage(record, context)]


# ---------------- 单一渲染源（决策 D-33）----------------


def test_markdown_and_xlsx_consume_same_sections(env):
    """两格式内容一致是**结构性质**：都来自 report_sections()。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    sections = report_sections(model)
    md = render_markdown(model, sections)
    rows = render_xlsx_table(model, sections)

    # 抽若干内容项做逐项对等断言（不是"都调了同一个函数"这种字面声明）
    assert "报告头与规则包坐标" in md
    assert "覆盖核查明细" in md
    flat = ["\t".join(r) for r in rows]
    assert any("覆盖核查明细" in row for row in flat)
    # 章节标题在两格式里都出现
    for section in sections:
        assert section.title in md
        assert any(section.title in row for row in flat)


def test_verdict_label_appears_in_both_formats(env):
    context, results = _coverage(env, items=("A1",))  # 缺 A2 → partial
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    flat = ["\t".join(r) for r in render_xlsx_table(model)]
    assert "部分符合" in md
    assert any("部分符合" in row for row in flat)


# ---------------- 字节可复现（决策 D-42：必须实测）----------------


def test_render_markdown_is_byte_reproducible(env):
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    first = render_markdown(model).encode("utf-8")
    second = render_markdown(model).encode("utf-8")
    assert first == second


def test_render_xlsx_is_byte_reproducible(env):
    """XLSX 必须逐字节可复现（自写 writer 钉死时间戳与宿主标识，决策 D-06）。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    first = render_xlsx_bytes(model)
    second = render_xlsx_bytes(model)
    assert first == second


def test_xlsx_zip_entries_have_fixed_timestamps_and_create_system(env):
    """zip 容器层：时间戳与 create_system 固定（跨平台字节一致）。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    data = render_xlsx_bytes(model)
    with zipfile.ZipFile(_BytesReader(data)) as zf:
        assert zf.namelist()
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0), info.filename
            assert info.create_system == 0, info.filename
            assert info.compress_type == zipfile.ZIP_STORED, info.filename


def test_export_report_two_runs_same_hashes(env):
    """export_report 两次导出：报告 sha256 逐个一致。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    out1 = env["tmp_path"] / "o1"
    out2 = env["tmp_path"] / "o2"
    r1 = export_report(model, str(out1))
    r2 = export_report(model, str(out2))
    assert r1["sha256"] == r2["sha256"]


# ---------------- 无外链（决策 D-34）----------------


def test_markdown_has_no_external_links(env):
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    # 正文不得出现 Markdown 链接语法（URL 只作纯文本落在参数来源块）
    assert "](" not in md
    assert "](http" not in md


def test_xlsx_has_no_external_relationships(env):
    """XLSX 无 TargetMode="External"、无 w:hyperlink（决策 D-34）。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    data = render_xlsx_bytes(model)
    with zipfile.ZipFile(_BytesReader(data)) as zf:
        for name in zf.namelist():
            content = zf.read(name).decode("utf-8", "replace")
            assert 'TargetMode="External"' not in content
            assert "w:hyperlink" not in content
        assert "xl/worksheets/sheet1.xml" in zf.namelist()


# ---------------- 显式"未启用"（决策 D-35）----------------


def test_disabled_sections_are_explicitly_stated(env):
    """未启用的章节必须显式写出，不留空（"没查"≠"查了没问题"）。"""
    context, _results = _coverage(env)
    model = build_report_model(context=context, generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    assert "本次导出未启用跨轮对账" in md
    assert "本次导出未启用批量扫描" in md
    assert "本次导出未启用覆盖核查" in md


def test_no_failed_items_is_explicitly_stated(env):
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    # 无 scan_result → 走"未启用批量扫描"；显式写清，不留空
    md = render_markdown(model)
    assert "未启用批量扫描" in md


# ---------------- 溯源与参数来源块 ----------------


def test_parameter_source_block_present(env):
    """报告必须含参数来源块（发布机关/文号/URL/抓取日期），决策 D-33/F5。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    assert "参数来源块" in md
    assert "抓取日期" in md
    sources = model.parameter_sources
    assert sources and all("fetched" in s for s in sources)


def test_report_header_states_ruleset_coordinate(env):
    """报告头固定输出规则包坐标（FR-F4）。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               ruleset_id="SYN-TEST", generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    assert "规则包坐标" in md
    assert "SYN-TEST" in md


def test_disclaimer_present(env):
    """免责声明强制（边界红线）。"""
    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    md = render_markdown(model)
    assert "不构成医学意见" in md
    assert "职业病诊断" in md


def test_evidence_contains_report_self_fingerprint(env):
    """证据链含报告**自身** sha256 → 改动报告即可检出（FR-F2）。"""
    from ohscheck.report.evidence import verify_evidence

    context, results = _coverage(env)
    model = build_report_model(coverage_results=results, context=context,
                               generated_at="2026-10-14T00:00:00")
    out = env["tmp_path"] / "out"
    info = export_report(model, str(out), ruleset_id="SYN-TEST")

    payload = load_path(info["evidence"])
    names = {item["path"] for item in payload["outputs"]}
    assert "report.md" in names and "report.xlsx" in names
    assert payload["generated_at"] is None  # 不写时间 → 保字节可复现

    assert verify_evidence(info["evidence"])["ok"] is True

    # 篡改报告 → 证据链检出
    with open(info["markdown"], "ab") as fh:
        fh.write(b"\ntampered\n")
    result = verify_evidence(info["evidence"])
    assert result["ok"] is False
    assert "report.md" in result["mismatched"]


class _BytesReader:
    """把 bytes 包成 file-like，供 zipfile 读取（无需落盘）。"""

    def __init__(self, data):
        import io

        self._io = io.BytesIO(data)

    def __getattr__(self, name):
        return getattr(self._io, name)
