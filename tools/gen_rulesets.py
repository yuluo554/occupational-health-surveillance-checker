#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""监护规则包生成器（**冻结产物唯一写入者**，决策 D-26）。

产出 data/rules/：双版本规则集 + manifest。

**M0 初态纪律**：全部条目 `status=pending` 且承载值为 `null`——
未挂原文核对不得落库/生效/进入核查路径（plan/05 §1.1）。
M1 起由本脚本从 `data/knowledge/` 的逐条核对记录填充 verified 条目。

纪律：
  * 禁 stdlib random / 禁 set 迭代序 / 禁系统时钟进产物；
  * 落盘 write_bytes + 显式 LF；再生成逐字节一致（--check 守门）。

用法：
    py -3.8 tools/gen_rulesets.py            # 生成
    py -3.8 tools/gen_rulesets.py --check    # 再生成并断言逐字节一致
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ohscheck import paths  # noqa: E402
from ohscheck.loaders import dumps_stable, write_bytes_lf  # noqa: E402
from ohscheck.rules.loader import file_sha256  # noqa: E402
from ohscheck.rules.schema import validate_manifest, validate_ruleset  # noqa: E402

# 切口与版本坐标（决策 D-10：代码零硬编码于此；引擎读 manifest.cutover）
CUTOVER = {"date": "2026-08-01", "before": "GBZ188-2014", "after": "GBZ188-2025"}

BASIS_2025 = {
    "doc_code": "GBZ 188—2025",
    "doc_title": "职业健康监护技术规范",
    "issuer": "国家卫生健康委员会",
    "doc_number": "国卫通〔2025〕10 号",
    "published": "2025-08-20",
    "effective_from": "2026-08-01",
    "replaces": "GBZ 188—2014",
    "url": "https://www.gov.cn/zhengce/zhengceku/202509/P020250906581488346891.pdf",
    "fetched": "2026-10-14",
}

BASIS_2014 = {
    "doc_code": "GBZ 188—2014",
    "doc_title": "职业健康监护技术规范（旧版，历史年度对照用）",
    "issuer": "",
    "doc_number": "",
    "published": "",
    "effective_from": "2014-12-15",
    "replaces": "",
    "url": "",
    "fetched": "2026-10-14",
}

# 首期范围：GBZ 188—2025 第 5 章（化学因素）与第 6 章（物理因素）主要危害因素。
#
# ⬜ M1 待办：这里只登记**节次坐标骨架**（factor_id 分配与章节归属），
#    危害因素名称/项目/周期一律待 M1 逐条挂官方原文核对后填充。
#    坐标本身取自 GBZ 188—2025 第 5/6 章节次结构（93 个 5.x/6.x 节次已解析，
#    见 data/README.md §二 #2 解析统计）。
#
# 结构：[章节, 节序号列表长度]（节内序号 1..n 为各危害因素）
CHAPTER_PLAN = {
    "5": 24,  # 第 5 章 接触化学因素（主要危害因素节次，M1 逐条核对后确定准确条数）
    "6": 8,   # 第 6 章 接触物理因素
}


def _pending_source():
    """pending 条目的 source 占位：字段齐全但为空（schema 要求字段存在）。"""
    return {"doc": "", "clause": "", "url": "", "fetched": ""}


def _pending_block(clause=""):
    return {"status": "pending", "basis": "", "source": _pending_source()}


def _pending_factor(chapter, index, category):
    fid = "%s.%d.0" % (chapter, index)
    return {
        "factor_id": fid,
        "factor_code": "PENDING_%s_%02d" % (chapter, index),
        # 名称占位：坐标已知但危害因素名称待 M1 逐条挂原文核对后填充。
        # 占位文本显式标"待核对"，不得被读成已核对内容。
        "factor_name": "待核对（第 %s 章 第 %d 节）" % (chapter, index),
        "chapter": chapter,
        "category": category,
        "eligibility": {
            "kind": "pending",
            "threshold": None,
            "unit": "",
            "comparator": "",
            "status": "pending",
            "basis": "",
            "source": _pending_source(),
        },
        "target_diseases": [],
        "exposed_population": "",
        "examinations": {
            key: {
                "required_items": [],
                "supplementary_items": [],
                "optional_items": [],
                "status": "pending",
                "basis": "",
                "source": _pending_source(),
            }
            for key in ("pre_placement", "periodic", "post_placement", "emergency")
        },
        "period": {
            "kind": "pending",
            "value": None,
            "status": "pending",
            "basis": "",
            "note": "",
            "source": _pending_source(),
        },
        "status": "pending",
        "source": _pending_source(),
    }


def _factors():
    out = []
    out.extend(
        _pending_factor("5", i, "chemical") for i in range(1, CHAPTER_PLAN["5"] + 1)
    )
    out.extend(
        _pending_factor("6", i, "physical") for i in range(1, CHAPTER_PLAN["6"] + 1)
    )
    return out


def ruleset_2025():
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "ruleset_id": CUTOVER["after"],
        "status": "scaffold",  # M0 骨架：全部条目 pending
        "basis": BASIS_2025,
        "chapters": ["5", "6"],
        # 选检项目口径由数据声明（新标删除上岗前/在岗期间/离岗时选检项，仅应急保留）
        "optional_items_policy": "emergency_only",
        "alias_map": {"status": "pending", "source": _pending_source(), "map": {}},
        "factors": _factors(),
    }


def ruleset_2014():
    """2014 版：**差异导向的骨架**（决策 D-28）。

    旧版官方全文预览已下架 → 以 2025 版前言"主要技术变化"逐条引述为对照依据，
    **不作完整重述**；凡前言未引述的条目保持 pending。
    """
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "ruleset_id": CUTOVER["before"],
        "status": "scaffold",
        "basis": BASIS_2014,
        "chapters": ["5", "6"],
        "optional_items_policy": "any",
        "alias_map": {"status": "pending", "source": _pending_source(), "map": {}},
        "factors": _factors(),
    }


def manifest(files):
    """（保留供外部引用；主通路走 main() 内的 build_manifest_text）"""
    return _build_manifest_obj(files)


def _build_manifest_obj(texts):
    entries = []
    for ruleset_id, filename in (
        (CUTOVER["before"], "ruleset-2014.json"),
        (CUTOVER["after"], "ruleset-2025.json"),
    ):
        data = texts[filename].encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        obj = ruleset_2014() if ruleset_id == CUTOVER["before"] else ruleset_2025()
        counts = {"verified": 0, "pending": len(obj["factors"]), "input_required": 0}
        entries.append(
            {
                "ruleset_id": ruleset_id,
                "file": filename,
                "sha256": sha,
                "factor_count": len(obj["factors"]),
                "status_counts": counts,
            }
        )
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "generated_by": "tools/gen_rulesets.py",
        "note": "M0 骨架：全部条目 status=pending，未挂原文核对不得进入核查路径。",
        "cutover": CUTOVER,
        "rulesets": entries,
        "benchmark_thresholds": {
            "matrix_accuracy_min": 0.95,
            "coverage_accuracy_min": 1.0,
            "compare_accuracy_min": 1.0,
            "false_positive_max": 0,
            "max_runtime_seconds": 1.0,
        },
    }


def _rules_dir():
    root = paths.find_data_dir()
    if root is None:
        print("错误：未找到 data/ 目录。")
        raise SystemExit(2)
    return os.path.join(root, "rules")


def ruleset_texts():
    return {
        "ruleset-2025.json": dumps_stable(ruleset_2025()),
        "ruleset-2014.json": dumps_stable(ruleset_2014()),
    }


def build_outputs():
    """产出最终落盘映射（manifest 的 sha256 需在规则集写盘后计算）。

    落盘顺序：先写两份规则集 → 再算 sha256 → 再写 manifest。
    为保证"再生成逐字节一致"，manifest 的 sha256 必须来自**将写入的同一批字节**：
    因此先写出规则集文件，再读回其 sha256 填进 manifest。
    """
    return ruleset_texts()


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
    root = _rules_dir()
    texts = build_outputs()

    def build_manifest_text():
        # 用将写入的字节（而非磁盘现值）算 sha256，保证首生成/再生成都自洽
        return dumps_stable(_build_manifest_obj(texts))

    outputs = dict(texts)
    outputs["manifest.json"] = build_manifest_text()

    # 自校验
    import json

    for name, text in outputs.items():
        obj = json.loads(text)
        if name == "manifest.json":
            validate_manifest(obj)
        else:
            validate_ruleset(obj)

    if not check:
        for rel in ("ruleset-2014.json", "ruleset-2025.json", "manifest.json"):
            write_bytes_lf(os.path.join(root, rel), outputs[rel])
        print("已生成 data/rules/（%d 个文件，全部条目 pending）" % len(outputs))
        for rel in sorted(outputs):
            print("  %s  sha256=%s" % (rel, file_sha256(os.path.join(root, rel))[:16]))
        return 0

    mismatch = []
    for rel, text in sorted(outputs.items()):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            mismatch.append(rel + "（缺失）")
            continue
        with open(path, "rb") as fh:
            if fh.read().decode("utf-8") != text:
                mismatch.append(rel + "（内容不一致）")
    if mismatch:
        print("FROZEN_RULESETS_MISMATCH: %s" % "; ".join(mismatch))
        return 1
    print("FROZEN_RULESETS_OK: %d 个文件再生成逐字节一致" % len(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
