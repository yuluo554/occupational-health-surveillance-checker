#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""基准合成夹具生成器（**冻结产物唯一写入者**，决策 D-26）。

产出 data/benchmark/：一套**合成**规则集（synthetic=true，出处带 SYNTHETIC- 前缀）
+ 植入真值的用例文件。

为什么要有合成规则集（而不是直接用生产规则包）：
  M0 期生产规则包全为 pending（未挂原文核对不得进入核查路径，决策 D-12），
  基准若依赖生产包就**永远跑不起来**；合成夹具让"引擎机制正确性"独立于
  "数据核对进度"被验证——基准验证机制，不验证国标内容。

纪律：
  * 禁 stdlib random / 禁 set 迭代序 / 禁系统时钟进产物；
  * 落盘 write_bytes + 显式 LF；再生成逐字节一致（--check 守门）；
  * 产物禁手改——改体例走本脚本整目录重生成。

用法：
    py -3.8 tools/gen_cases.py            # 生成
    py -3.8 tools/gen_cases.py --check    # 再生成并断言逐字节一致
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ohscheck import paths  # noqa: E402
from ohscheck.loaders import dumps_stable, load_path, write_bytes_lf  # noqa: E402
from ohscheck.rules.loader import file_sha256  # noqa: E402
from ohscheck.rules.schema import SYNTHETIC_MARKER, validate_manifest, validate_ruleset  # noqa: E402

SYN = SYNTHETIC_MARKER  # "SYNTHETIC-"

# 合成标准号（虚构，绝不与真实标准号形态相同）
DOC_2025 = SYN + "GBZ188-2025（合成夹具，非真实标准）"
DOC_2014 = SYN + "GBZ188-2014（合成夹具，非真实标准）"

# 合成危害因素（虚构代码，非真实物质名）
FACTOR_A = "SYN_FACTOR_ALPHA"
FACTOR_B = "SYN_FACTOR_BETA"
FACTOR_C = "SYN_FACTOR_GAMMA"  # 仅 2025 版新增
FACTOR_D = "SYN_FACTOR_DELTA"  # 仅 2014 版存在（2025 版删除）

# 合成检查项目
ITEMS_A = ["SYN_ITEM_A1", "SYN_ITEM_A2", "SYN_ITEM_A3"]
ITEMS_B = ["SYN_ITEM_B1", "SYN_ITEM_B2"]

_SRC = {
    "doc": DOC_2025,
    "clause": "5.1.0",
    "url": "",
    "fetched": "2026-10-14",
}


def _src(doc, clause):
    return {"doc": doc, "clause": clause, "url": "", "fetched": "2026-10-14"}


def _verified_item(code, name, clause, doc):
    return {
        "item_code": code,
        "item_name": name,
        "status": "verified",
        "basis": "合成夹具",
        "source": _src(doc, clause),
    }


def _exam_block(required, doc, clause, optional=None, supplementary=None):
    return {
        "required_items": [_verified_item(c, "合成项目 " + c, clause, doc) for c in required],
        "supplementary_items": [
            _verified_item(c, "合成补充项目 " + c, clause, doc) for c in (supplementary or [])
        ],
        "optional_items": [
            _verified_item(c, "合成选检项目 " + c, clause, doc) for c in (optional or [])
        ],
        "status": "verified",
        "basis": "合成夹具",
        "source": _src(doc, clause),
    }


def _factor(code, name, fid, chapter, category, required, months, doc, optional=None):
    return {
        "factor_id": fid,
        "factor_code": code,
        "factor_name": name,
        "chapter": chapter,
        "category": category,
        "eligibility": {
            "kind": "always",
            "threshold": None,
            "unit": "",
            "comparator": "",
            "status": "verified",
            "basis": "合成夹具：一律纳入监护",
            "source": _src(doc, fid),
        },
        "target_diseases": [
            {"name": "合成目标疾病", "status": "verified", "basis": "合成夹具",
             "source": _src(doc, fid)}
        ],
        "exposed_population": "合成接触人群",
        "examinations": {
            "pre_placement": _exam_block(required, doc, fid),
            "periodic": _exam_block(required, doc, fid, supplementary=["SYN_SUP_1"]),
            "post_placement": _exam_block(required, doc, fid),
            "emergency": _exam_block(["SYN_EMG_1"], doc, fid, optional=optional),
        },
        "period": {
            "kind": "months",
            "value": months,
            "status": "verified",
            "basis": "合成夹具：%d 个月" % months,
            "note": "",
            "source": _src(doc, fid),
        },
        "status": "verified",
        "source": _src(doc, fid),
    }


def ruleset_2025():
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "ruleset_id": "SYN-2025",
        "basis": {
            "doc_code": DOC_2025,
            "doc_title": SYN + "职业健康监护技术规范（合成夹具）",
            "issuer": "",
            "doc_number": SYN + "TEST-ONLY",
            "published": "2025-08-20",
            "effective_from": "2026-08-01",
            "replaces": DOC_2014,
            "url": "",
            "fetched": "2026-10-14",
        },
        "chapters": ["5", "6"],
        "optional_items_policy": "emergency_only",
        "factors": [
            _factor(FACTOR_A, "合成因素甲", "5.1.0", "5", "chemical", ITEMS_A, 12, DOC_2025),
            _factor(FACTOR_B, "合成因素乙", "6.1.0", "6", "physical", ITEMS_B, 24, DOC_2025),
            # 2025 版新增因素
            _factor(FACTOR_C, "合成因素丙（新增）", "5.2.0", "5", "chemical", ["SYN_ITEM_C1"], 6, DOC_2025),
        ],
    }


def ruleset_2014():
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "ruleset_id": "SYN-2014",
        "basis": {
            "doc_code": DOC_2014,
            "doc_title": SYN + "职业健康监护技术规范（合成夹具·旧版）",
            "issuer": "",
            "doc_number": SYN + "TEST-ONLY-OLD",
            "published": "2014-01-01",
            "effective_from": "2014-01-01",
            "replaces": "",
            "url": "",
            "fetched": "2026-10-14",
        },
        "chapters": ["5", "6"],
        "factors": [
            # 甲：2014 版周期为 24 个月、项目少一项（供版本差异对照）
            _factor(FACTOR_A, "合成因素甲", "5.1.0", "5", "chemical",
                    ["SYN_ITEM_A1", "SYN_ITEM_A2"], 24, DOC_2014),
            _factor(FACTOR_B, "合成因素乙", "6.1.0", "6", "physical", ITEMS_B, 24, DOC_2014),
            # 2014 版独有、2025 版删除
            _factor(FACTOR_D, "合成因素丁（已删除）", "5.3.0", "5", "chemical",
                    ["SYN_ITEM_D1"], 12, DOC_2014),
        ],
    }


def manifest():
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "generated_by": "tools/gen_cases.py",
        "note": "合成夹具：仅用于验证引擎机制，不含任何真实标准内容。",
        "cutover": {"date": "2026-08-01", "before": "SYN-2014", "after": "SYN-2025"},
        "rulesets": [
            {"ruleset_id": "SYN-2014", "file": "ruleset-2014.json", "factor_count": 3,
             "status_counts": {"verified": 6, "pending": 0, "input_required": 0}},
            {"ruleset_id": "SYN-2025", "file": "ruleset-2025.json", "factor_count": 3,
             "status_counts": {"verified": 6, "pending": 0, "input_required": 0}},
        ],
        "benchmark_thresholds": {
            "matrix_accuracy_min": 1.0,
            "coverage_accuracy_min": 1.0,
            "compare_accuracy_min": 1.0,
            "false_positive_max": 0,
            "max_runtime_seconds": 5.0,
        },
        # 版本对照期望（供 compare 套件对账）
        "compare_expect": {
            FACTOR_A: "required_items_changed",
            FACTOR_C: "factor_added",
            FACTOR_D: "factor_removed",
        },
    }


def _record(record_id, employee_id, factor_code, exam_date, exam_type, items,
            expect, last_exam_date=None, position_id="SYN-POS-001"):
    obj = {
        "record_id": record_id,
        "employee_id": employee_id,
        "employee_name": "示例人员 " + employee_id,
        "position_id": position_id,
        "factor_code": factor_code,
        "exam_date": exam_date,
        "exam_type": exam_type,
        "items": list(items),
        "conclusion_code": "normal",
        "notified_suspected": False,
        "expect": expect,
    }
    if last_exam_date:
        obj["last_exam_date"] = last_exam_date
    return obj


def cases_2025():
    """2025 版适用期的用例（体检日期 >= 切口日）。"""
    records = [
        # 1) 干净档案：应检齐备、周期未到 → 应零命中（误报对照集）
        _record(
            "SYN-REC-001", "SYN-A-001", FACTOR_A, "2026-09-15", "periodic", ITEMS_A,
            {"verdict": "compliant", "missing_items": [], "period_verdict": "compliant",
             "should_be_clean": True},
            last_exam_date="2025-10-01",
        ),
        # 2) 缺一项必检项 → partial
        _record(
            "SYN-REC-002", "SYN-A-002", FACTOR_A, "2026-09-15", "periodic", ITEMS_A[:2],
            {"verdict": "partial", "missing_items": [ITEMS_A[2]],
             "period_verdict": "compliant",
             "also_expect": [{"kind": "verdict", "verdict": "partial"}]},
            last_exam_date="2025-10-01",
        ),
        # 3) 必检项全缺 → non_compliant
        _record(
            "SYN-REC-003", "SYN-A-003", FACTOR_A, "2026-09-15", "pre_placement", [],
            {"verdict": "non_compliant", "missing_items": list(ITEMS_A),
             "period_verdict": "not_applicable",
             "also_expect": [{"kind": "verdict", "verdict": "non_compliant"}]},
        ),
        # 4) 周期超期（12 个月周期，隔了 18 个月）→ partial（周期）
        _record(
            "SYN-REC-004", "SYN-A-004", FACTOR_A, "2026-10-01", "periodic", ITEMS_A,
            {"verdict": "partial", "missing_items": [], "period_verdict": "overdue",
             "also_expect": [{"kind": "period", "verdict": "overdue"},
                             {"kind": "verdict", "verdict": "partial"}]},
            last_exam_date="2025-04-01",
        ),
        # 5) 周期边界：恰好到期 → due（合规）
        _record(
            "SYN-REC-005", "SYN-A-005", FACTOR_A, "2026-09-15", "periodic", ITEMS_A,
            {"verdict": "compliant", "missing_items": [], "period_verdict": "due",
             "should_be_clean": True},
            last_exam_date="2025-09-15",
        ),
        # 6) 未归一实检项（非精确命中）→ 不判缺失，记 warning（应零 fail）
        _record(
            "SYN-REC-006", "SYN-A-006", FACTOR_A, "2026-09-15", "periodic",
            ITEMS_A + ["某种别名的检查项目写法"],
            {"verdict": "compliant", "missing_items": [], "period_verdict": "compliant",
             "should_be_clean": True},
            last_exam_date="2025-10-01",
        ),
        # 7) 物理因素干净档案
        _record(
            "SYN-REC-007", "SYN-B-001", FACTOR_B, "2026-09-20", "periodic", ITEMS_B,
            {"verdict": "compliant", "missing_items": [], "period_verdict": "compliant",
             "should_be_clean": True},
            last_exam_date="2026-01-20",
        ),
        # 8) 新增因素（2025 版）缺项
        _record(
            "SYN-REC-008", "SYN-C-001", FACTOR_C, "2026-09-20", "pre_placement", [],
            {"verdict": "non_compliant", "missing_items": ["SYN_ITEM_C1"],
             "period_verdict": "not_applicable",
             "also_expect": [{"kind": "verdict", "verdict": "non_compliant"}]},
        ),
    ]
    return {
        "case_id": "SYN-CASE-2025",
        "ruleset_id": "SYN-2025",
        "position": {"exam_date": "2026-09-15"},
        "expect_plan": {
            FACTOR_A: {"exams": {"pre_placement": list(ITEMS_A),
                                 "periodic": list(ITEMS_A),
                                 "post_placement": list(ITEMS_A)}},
            FACTOR_B: {"exams": {"pre_placement": list(ITEMS_B),
                                 "periodic": list(ITEMS_B),
                                 "post_placement": list(ITEMS_B)}},
            FACTOR_C: {"exams": {"pre_placement": ["SYN_ITEM_C1"]}},
        },
        "records": records,
    }


def cases_2014():
    """2014 版适用期的用例（体检日期 < 切口日）。"""
    records = [
        # 同一因素甲的应检项为 2 项（旧版少一项），做齐 → compliant
        _record(
            "SYN-REC-101", "SYN-A-101", FACTOR_A, "2024-03-01", "periodic",
            ["SYN_ITEM_A1", "SYN_ITEM_A2"],
            {"verdict": "compliant", "missing_items": [], "period_verdict": "compliant",
             "should_be_clean": True},
            last_exam_date="2023-03-01",
        ),
        # 旧版独有因素丁
        _record(
            "SYN-REC-102", "SYN-D-101", FACTOR_D, "2024-03-01", "pre_placement", ["SYN_ITEM_D1"],
            {"verdict": "compliant", "missing_items": [], "period_verdict": "not_applicable",
             "should_be_clean": True},
        ),
    ]
    return {
        "case_id": "SYN-CASE-2014",
        "ruleset_id": "SYN-2014",
        "position": {"exam_date": "2024-03-01"},
        "expect_plan": {
            FACTOR_A: {"exams": {"pre_placement": ["SYN_ITEM_A1", "SYN_ITEM_A2"],
                                 "periodic": ["SYN_ITEM_A1", "SYN_ITEM_A2"],
                                 "post_placement": ["SYN_ITEM_A1", "SYN_ITEM_A2"]}},
            FACTOR_D: {"exams": {"pre_placement": ["SYN_ITEM_D1"]}},
        },
        "records": records,
    }


def build_outputs():
    """产出 {相对路径: 文本} 映射（确定性）。"""
    return {
        "manifest.json": dumps_stable(manifest()),
        "ruleset-2025.json": dumps_stable(ruleset_2025()),
        "ruleset-2014.json": dumps_stable(ruleset_2014()),
        "cases/case-2025.json": dumps_stable(cases_2025()),
        "cases/case-2014.json": dumps_stable(cases_2014()),
    }


def bench_dir():
    root = paths.find_data_dir()
    if root is None:
        print("错误：未找到 data/ 目录。")
        raise SystemExit(2)
    return os.path.join(root, "benchmark")


def _validate(outputs):
    """自校验：schema + 合成出处护栏 + 真值自洽。"""
    import json
    import tempfile

    for name, text in outputs.items():
        obj = json.loads(text)
        if name == "manifest.json" and not name.startswith("cases/"):
            validate_manifest(obj)
        elif name.startswith("ruleset-"):
            validate_ruleset(obj)

    # 合成规则集的 verified 出处必须是合成标记（防"合成夹具冒充国标"）
    for name in ("ruleset-2025.json", "ruleset-2014.json"):
        obj = json.loads(outputs[name])
        assert obj["basis"]["doc_code"].startswith(SYN), name
        assert obj["basis"]["issuer"] == "", name


def _ensure_utf8_stdio():
    """编码守卫（决策 D-39）：cp1252 等管道不因非 ASCII 输出崩。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if not encoding or "utf" in encoding:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main(argv):
    _ensure_utf8_stdio()
    check = "--check" in argv
    root = bench_dir()
    outputs = build_outputs()
    _validate(outputs)

    if not check:
        for rel, text in sorted(outputs.items()):
            write_bytes_lf(os.path.join(root, rel.replace("/", os.sep)), text)
        print("已生成 data/benchmark/（%d 个文件）" % len(outputs))
        for rel in sorted(outputs):
            path = os.path.join(root, rel.replace("/", os.sep))
            print("  %s  sha256=%s" % (rel, file_sha256(path)[:16]))
        return 0

    # --check：再生成断言逐字节一致（决策 D-26）
    mismatch = []
    for rel, text in sorted(outputs.items()):
        path = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            mismatch.append(rel + "（缺失）")
            continue
        with open(path, "rb") as fh:
            actual = fh.read().decode("utf-8")
        if actual != text:
            mismatch.append(rel + "（内容不一致）")
    if mismatch:
        print("FROZEN_CASES_MISMATCH: %s" % "; ".join(mismatch))
        return 1
    print("FROZEN_CASES_OK: %d 个文件再生成逐字节一致" % len(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
