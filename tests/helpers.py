"""测试夹具助手：本仓自有的合成规则集与档案。

**纪律**：测试夹具一律**合成**（synthetic=true、出处带 SYNTHETIC- 前缀），
绝不写入任何真实标准内容（数据纪律，plan/02 §4.4）。
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def repo_root():
    return _ROOT


def data_dir():
    return os.path.join(_ROOT, "data")


def bench_dir():
    return os.path.join(_ROOT, "data", "benchmark")


SYN = "SYNTHETIC-"


def _src(clause):
    return {"doc": SYN + "TESTSPEC", "clause": clause, "url": "", "fetched": "2026-10-14"}


def _item(code, clause="9.9.9"):
    return {
        "item_code": code,
        "item_name": SYN + "项目 " + code,
        "status": "verified",
        "basis": SYN + "测试",
        "source": _src(clause),
    }


def _block(required, optional=None, clause="9.9.9"):
    return {
        "required_items": [_item(c, clause) for c in required],
        "supplementary_items": [],
        "optional_items": [_item(c, clause) for c in (optional or [])],
        "status": "verified",
        "basis": SYN + "测试",
        "source": _src(clause),
    }


def make_factor(code="T_FACTOR", fid="5.9.0", months=12, required=("T_ITEM_1",),
                kind="always", threshold=None, comparator=">=", unit="mg/m3",
                factor_status="verified", exam_status="verified", period_status="verified"):
    """构造一个合成危害因素条目。

    factor_status / exam_status / period_status 用于**注入 pending**，
    测试门控行为（决策 D-12：未核对不得进入核查路径）。
    """
    elig = {
        "kind": kind,
        "threshold": threshold if kind == "threshold" else None,
        "unit": unit,
        "comparator": comparator if kind == "threshold" else "",
        "status": factor_status,
        "basis": SYN + "一律纳入监护",
        "source": _src(fid),
    }
    exam_required = [_item(c, fid) for c in required] if exam_status == "verified" else []
    exams = {
        key: {
            "required_items": list(exam_required),
            "supplementary_items": [],
            "optional_items": [],
            "status": exam_status,
            "basis": SYN + "测试",
            "source": _src(fid),
        }
        for key in ("pre_placement", "periodic", "post_placement", "emergency")
    }
    return {
        "factor_id": fid,
        "factor_code": code,
        "factor_name": SYN + "因素 " + code,
        "chapter": fid.split(".")[0],
        "category": "chemical",
        "eligibility": elig,
        "target_diseases": [],
        "exposed_population": "",
        "examinations": exams,
        "period": {
            "kind": "months",
            "value": months if period_status == "verified" else None,
            "status": period_status,
            "basis": SYN + "测试",
            "note": "",
            "source": _src(fid),
        },
        "status": factor_status,
        "source": _src(fid),
    }


def make_ruleset(factors=None, ruleset_id="SYN-TEST", effective_from="2026-08-01",
                 optional_items_policy="any"):
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "ruleset_id": ruleset_id,
        "basis": {
            "doc_code": SYN + "TESTSPEC",
            "doc_title": SYN + "合成测试规范",
            "issuer": "",
            "doc_number": SYN + "TEST",
            "published": "2026-01-01",
            "effective_from": effective_from,
            "replaces": "",
            "url": "",
            "fetched": "2026-10-14",
        },
        "chapters": ["5"],
        "optional_items_policy": optional_items_policy,
        "alias_map": {"status": "pending", "source": _src("9"), "map": {}},
        "factors": list(factors or [make_factor()]),
    }


def make_manifest(rulesets=None, cutover=None):
    entries = []
    for rid, filename, count in (rulesets or [("SYN-TEST", "ruleset.json", 1)]):
        entries.append(
            {
                "ruleset_id": rid,
                "file": filename,
                "sha256": "",
                "factor_count": count,
                "status_counts": {"verified": 0, "pending": 0, "input_required": 0},
            }
        )
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "generated_by": "tests",
        "cutover": cutover or {"date": "2026-08-01", "before": "SYN-OLD", "after": "SYN-NEW"},
        "rulesets": entries,
        "benchmark_thresholds": {
            "matrix_accuracy_min": 1.0,
            "coverage_accuracy_min": 1.0,
            "compare_accuracy_min": 1.0,
            "false_positive_max": 0,
            "max_runtime_seconds": 30.0,
        },
    }


def write_json(path, obj):
    """以 LF 写 JSON（3.8 兼容）。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    with open(path, "wb") as fh:
        fh.write((text.replace("\r\n", "\n") + "\n").encode("utf-8"))
    return path


def make_record(record_id="REC-1", employee_id="SYN-A-001", factor_code="T_FACTOR",
                exam_date="2026-09-15", exam_type="periodic", items=("T_ITEM_1",),
                last_exam_date=None, conclusion_code="normal"):
    obj = {
        "record_id": record_id,
        "employee_id": employee_id,
        "employee_name": SYN + "人员 " + employee_id,
        "position_id": "POS-1",
        "factor_code": factor_code,
        "exam_date": exam_date,
        "exam_type": exam_type,
        "items": list(items),
        "conclusion_code": conclusion_code,
        "notified_suspected": False,
    }
    if last_exam_date:
        obj["last_exam_date"] = last_exam_date
    return obj


def make_temp_data_dir(base, factors=None, rulesets=None, cutover=None, thresholds=None):
    """在 base 下物化一个可被 CLI 使用的 data/ 目录（含 rules/manifest.json）。

    生产布局是 `data/rules/manifest.json`；基准夹具目录是扁平布局，二者用途不同，
    故 CLI 测试用具名临时目录而不是复用基准目录。

    cutover 缺省时把 before/after 都指向唯一那套规则集——这样按体检日期锚定
    必然命中它，测试无需关心切口日。需要测版本切换时显式传多套 rulesets 与 cutover。

    Returns:
        data 目录路径。
    """
    import os as _os

    rules_dir = _os.path.join(str(base), "rules")
    if not _os.path.isdir(rules_dir):
        _os.makedirs(rules_dir)

    if factors is None:
        factors = [make_factor()]
    if rulesets is None:
        rulesets = [("SYN-TEST", "ruleset.json", len(factors))]

    for rid, filename, _count in rulesets:
        obj = make_ruleset(factors, ruleset_id=rid)
        write_json(_os.path.join(rules_dir, filename), obj)

    if cutover is None:
        only = rulesets[0][0]
        cutover = {"date": "2026-08-01", "before": only, "after": only}

    manifest_obj = make_manifest(rulesets, cutover=cutover)
    if thresholds is not None:
        manifest_obj["benchmark_thresholds"] = thresholds
    # 填真实 sha256，便于报告 §9 参数来源块有值
    from ohscheck.rules.loader import file_sha256

    for entry in manifest_obj["rulesets"]:
        path = _os.path.join(rules_dir, entry["file"])
        if _os.path.isfile(path):
            entry["sha256"] = file_sha256(path)
    write_json(_os.path.join(rules_dir, "manifest.json"), manifest_obj)
    return str(base)
