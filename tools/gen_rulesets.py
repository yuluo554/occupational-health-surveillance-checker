#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""监护规则包生成器（**冻结产物唯一写入者**，决策 D-26）。

产出 data/rules/：双版本规则集 + manifest。

数据来源（M1 起）：
  * **2025 版**：`tools/gbz188_transcribe.py` 从官方 PDF 解析快照
    （`data/knowledge/raw/GBZ188-2025.layout.txt`）逐条转写，每个抽取值都经
    **原文逐字包含断言**（见 `assert_verbatim`）。第 5–7 章（化学/粉尘/物理）
    落 `verified` 明细；第 8–9 章（生物/特殊作业）只落**因素身份** verified，
    明细保持 `pending`——正好构成 M1-7 要验的"部分核对"混合态。
  * **2014 版**：差异导向骨架（决策 D-28）。旧版已废止、官方全文预览下架，
    故只承载 2025 版前言"主要技术变化"逐条引述的差异；未引述的条目一律 `pending`。

纪律：
  * 禁 stdlib random / 禁 set 迭代序 / 禁系统时钟进产物；
  * 落盘 write_bytes + 显式 LF；再生成逐字节一致（--check 守门）；
  * **产物禁手改**——改体例走本脚本整目录重生成。

用法：
    py -3.8 tools/gen_rulesets.py            # 生成
    py -3.8 tools/gen_rulesets.py --check    # 再生成并断言逐字节一致
"""

from __future__ import annotations

import hashlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

from ohscheck import paths  # noqa: E402
from ohscheck.loaders import dumps_stable, write_bytes_lf  # noqa: E402
from ohscheck.rules.loader import file_sha256  # noqa: E402
from ohscheck.rules.schema import validate_manifest, validate_ruleset  # noqa: E402

import gbz188_2014_delta as DELTA  # noqa: E402
import gbz188_transcribe as TR  # noqa: E402

# 切口与版本坐标（决策 D-10：代码零硬编码于此；引擎读 manifest.cutover）
CUTOVER = {"date": "2026-08-01", "before": "GBZ188-2014", "after": "GBZ188-2025"}

# 首期落 verified 明细的章节（化学 / 粉尘 / 物理）。
DETAIL_CHAPTERS = ("5", "6", "7")
# 只落因素身份、明细保持 pending 的章节（生物 / 特殊作业）。
IDENTITY_CHAPTERS = ("8", "9")

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
    # 待核对项 P-1（原发布文号与发布/实施日期）：两个官方渠道均未取到原文，
    # 按纪律**不填猜测值**，改以 effective_from_status=pending 显式声明（决策 D-13 同族）。
    "effective_from": "",
    "effective_from_status": "pending",
    "replaces": "",
    "url": "",
    "fetched": "2026-10-14",
}

# 人群界定依据（第 4.5 节『职业健康监护人群的界定原则』）——所有因素的适用性同源。
ELIGIBILITY_BASIS = "GBZ 188—2025 第 4.5 节（接触者一律纳入监护）"

# 2025 版前言中"新增"的 2025 版条款号（→ 2014 版不该有这些因素）。
def _foreword_added_clauses():
    """2025 版前言中点名"**新增危害因素**"的条款号（→ 2014 版不该有这些因素）。

    判别口径（写死，防误排除）：前言"增加了…"共三类，只有**第一类**是新增因素——
      * 『增加了接触…**作业人员的健康监护**』→ 新因素（取其条款号）；
      * 『增加了…作业人员的**应急/离岗时健康检查**』→ 只是给**已存在**因素加了时点
        （如 5.1.4 是 5.1 铅的应急检查）→ 不得把 5.1 整个排除；
      * 『增加了…补充检查项目 / 生物标志物检测 / 附录 X』 → 非因素级。
    故判据 = 条文含"健康监护"且**不含**"健康检查"。
    """
    out = set()
    for item in TR.foreword_changes():
        if item["kind"] != "added":
            continue
        text = item["text"]
        if "健康监护" not in text or "健康检查" in text:
            continue
        out.update(item["clauses"])
    return out


def _source(clause, doc_code=None, url=""):
    """构造 source 块（字段齐全，逐条挂节号）。"""
    return {
        "doc": doc_code or BASIS_2025["doc_code"],
        "clause": clause,
        "url": url,
        "fetched": BASIS_2025["fetched"],
    }


def _factor_code(factor_id):
    """因素代码 = 标准号 + 节号（确定、可 grep、零转写风险）。"""
    return "GBZ188-%s" % factor_id


def _verified_item(name, clause):
    """一个必检/补充/选检项目条目。

    项目代码取**标准原文的规范写法本身**（`item_code == item_name`）：
    这样档案里的实检项目可以直接按标准写法书写，匹配是精确字符串比对；
    写法差异（如"血细胞分析"vs"血常规"）交由显式别名表处理（决策 D-17）。
    """
    return {
        "item_code": name,
        "item_name": name,
        "status": "verified",
        "basis": "GBZ 188—2025",
        "source": _source(clause),
    }


def _exam_block(parsed_block, clause):
    """构造一个时点的检查内容块。"""
    items = {
        "required_items": [_verified_item(x, clause) for x in parsed_block["required"]],
        "supplementary_items": [_verified_item(x, clause) for x in parsed_block["supplementary"]],
        "optional_items": [_verified_item(x, clause) for x in parsed_block["optional"]],
    }
    if parsed_block["absent"]:
        # 该因素标准未设该时点检查：状态 verified（"确无此时点"是核对过的事实），
        # 项目全空——不是 pending（pending 表示"尚未核对"）。
        return {
            "required_items": [],
            "supplementary_items": [],
            "optional_items": [],
            "status": "verified",
            "basis": "GBZ 188—2025 未设该时点职业健康检查",
            "source": _source(clause),
        }
    return dict(
        items,
        status="verified",
        basis="GBZ 188—2025",
        source=_source(clause),
    )


def _target_diseases(parsed_block, clause):
    return [
        {
            "name": name,
            "status": "verified",
            "basis": "GBZ 188—2025",
            "source": _source(clause),
        }
        for name in parsed_block["diseases"]
    ]


def _verified_factor(parsed):
    """第 5–7 章因素：全字段 verified。"""
    sid = parsed["factor_id"]
    exams = {
        key: _exam_block(parsed["exams"][key], parsed["exams"][key]["basis_clause"])
        for key in TR.EXAM_KEYS
    }
    period = parsed["period"]
    if period["kind"] == "pending":
        # 本节无"在岗期间"时点 → 该因素无周期要求（非"未核对"）。
        period_block = {
            "kind": "none",
            "value": None,
            "status": "verified",
            "basis": "GBZ 188—2025 未设在岗期间检查，无检查周期要求",
            "note": "",
            "source": _source(sid),
        }
    elif period["kind"] == "input_required":
        period_block = {
            "kind": "input_required",
            "value": None,
            "status": "input_required",
            "basis": "周期按具体情形分档，规则包不承载单值：%s" % period["payload"][:200],
            "note": period["payload"],
            "source": _source(period["clause"] or sid),
        }
    else:
        period_block = {
            "kind": "months",
            "value": period["value"],
            "status": "verified",
            "basis": "GBZ 188—2025",
            "note": period["note"],
            "source": _source(period["clause"] or sid),
        }
    exposed = ""
    for key in TR.EXAM_KEYS:
        if parsed["exams"][key].get("exposed"):
            exposed = parsed["exams"][key]["exposed"]
            break
    return {
        "factor_id": sid,
        "factor_code": _factor_code(sid),
        "factor_name": parsed["name"],
        "chapter": parsed["chapter"],
        "category": parsed["category"],
        "eligibility": {
            "kind": "always",
            "threshold": None,
            "unit": "",
            "comparator": "",
            "status": "verified",
            "basis": ELIGIBILITY_BASIS,
            "source": _source("%s 及第 4.5 节" % sid),
        },
        "target_diseases": _target_diseases(parsed["exams"]["periodic"], sid)
        + _target_diseases(parsed["exams"]["pre_placement"], sid),
        "exposed_population": exposed,
        "examinations": exams,
        "period": period_block,
        "status": "verified",
        "source": _source(sid),
    }


def _identity_only_factor(parsed):
    """第 8–9 章因素：身份（名称/节号/类别）verified，明细一律 pending。

    门控语义（决策 D-12）：full 深度（plan/check）会拦在 eligibility.pending；
    minimal 深度（compare/bench）只看因素 status=verified → 放行。
    这正是 M1-7 要验的"部分核对"行为。
    """
    sid = parsed["factor_id"]

    def pending_block():
        return {
            "required_items": [],
            "supplementary_items": [],
            "optional_items": [],
            "status": "pending",
            "basis": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        }

    return {
        "factor_id": sid,
        "factor_code": _factor_code(sid),
        "factor_name": parsed["name"],
        "chapter": parsed["chapter"],
        "category": parsed["category"],
        "eligibility": {
            "kind": "pending",
            "threshold": None,
            "unit": "",
            "comparator": "",
            "status": "pending",
            "basis": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        },
        "target_diseases": [],
        "exposed_population": "",
        "examinations": {key: pending_block() for key in TR.EXAM_KEYS},
        "period": {
            "kind": "pending",
            "value": None,
            "status": "pending",
            "basis": "",
            "note": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        },
        "status": "verified",  # 身份已核对（名称/节号/类别），明细待核对
        "source": _source(sid),
    }


def ruleset_2025(parsed=None):
    """GBZ 188—2025 规则集（第 5–7 章明细 verified + 第 8–9 章身份 verified）。"""
    parsed = parsed if parsed is not None else TR.transcribe()
    factors = []
    for sid in sorted(parsed, key=lambda k: [int(x) for x in k.split(".")]):
        chapter = parsed[sid]["chapter"]
        if chapter in DETAIL_CHAPTERS:
            factors.append(_verified_factor(parsed[sid]))
        elif chapter in IDENTITY_CHAPTERS:
            factors.append(_identity_only_factor(parsed[sid]))
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "ruleset_id": CUTOVER["after"],
        "status": "partial",
        "basis": BASIS_2025,
        "chapters": list(DETAIL_CHAPTERS) + list(IDENTITY_CHAPTERS),
        # 选检项目口径由数据声明（新标删除上岗前/在岗期间/离岗时选检项，仅应急保留）
        "optional_items_policy": "emergency_only",
        "alias_map": {
            "status": "pending",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
            "map": {},
        },
        "factors": factors,
    }


def _pending_detail_factor(factor_id, factor_code, factor_name, chapter, category, basis_text):
    """2014 版差异骨架的"坐标型"因素：身份给出，明细 pending（值一律 null）。"""
    def pending_source(clause):
        return {"doc": BASIS_2014["doc_code"], "clause": clause, "url": "", "fetched": ""}

    def pending_block(clause, verified=False):
        if verified:
            return {
                "required_items": [],
                "supplementary_items": [],
                "optional_items": [],
                "status": "pending",
                "basis": "",
                "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
            }
        return {
            "required_items": [],
            "supplementary_items": [],
            "optional_items": [],
            "status": "pending",
            "basis": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        }

    return {
        "factor_id": factor_id,
        "factor_code": factor_code,
        "factor_name": factor_name,
        "chapter": chapter,
        "category": category,
        "eligibility": {
            "kind": "pending",
            "threshold": None,
            "unit": "",
            "comparator": "",
            "status": "pending",
            "basis": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        },
        "target_diseases": [],
        "exposed_population": "",
        "examinations": {key: pending_block(factor_id) for key in TR.EXAM_KEYS},
        "period": {
            "kind": "pending",
            "value": None,
            "status": "pending",
            "basis": "",
            "note": "",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
        },
        "status": "verified",
        "source": pending_source(basis_text),
    }


def ruleset_2014(parsed_2025=None):
    """GBZ 188—2014 规则集：**差异导向骨架**（决策 D-28）。

    构成：
      ① 2025 版第 5–9 章因素坐标**镜像**为 pending 骨架（提供结构对照基座），
         **但排除**前言点名"新增"的 2025 条款（2014 版无这些因素）；
      ② 前言点名"删除"的 2014 版因素（甲苯二异氰酸酯 5.44、结核病/肝炎病防治作业
         9.4/9.5）以身份落地——它们是 `compare` 的"因素被删除"侧。
    凡前言未引述的条目，其项目/周期一律 pending（**不作完整重述**）。

    **坐标重号处置**（真实数据现象，必须如实处理）：两版节号发生过位移——
    2014 版 5.44 是甲苯二异氰酸酯，而 2025 版 5.44 是二甲基甲酰胺；9.4/9.5 同理。
    故"被删除的 2014 版因素"用其**真实的 2014 版节号**（前言引述，可核对），
    与之重号的 2025 版镜像因素改用**占位坐标** `<节号>.0`（沿用 M0 的占位约定），
    以免同一规则集内坐标重复。占位坐标仅是唯一化手段，不代表真实 2014 版节号。
    """
    parsed_2025 = parsed_2025 if parsed_2025 is not None else TR.transcribe()
    added = _foreword_added_clauses()
    removed_ids = {entry["factor_id"] for entry in DELTA.REMOVED_FACTORS}

    factors = []
    for sid in sorted(parsed_2025, key=lambda k: [int(x) for x in k.split(".")]):
        if sid in added:
            continue  # 2025 版新增 → 2014 版不存在
        item = parsed_2025[sid]
        coordinate = sid + ".0" if sid in removed_ids else sid
        factors.append(
            _pending_detail_factor(
                coordinate,
                _factor_code(sid),  # 身份键与 2025 版一致 → compare 按 code 正确配对
                item["name"],
                item["chapter"],
                item["category"],
                sid,
            )
        )
    for entry in DELTA.REMOVED_FACTORS:
        factors.append(
            _pending_detail_factor(
                entry["factor_id"],
                entry["factor_code"],
                entry["factor_name"],
                entry["chapter"],
                entry["category"],
                entry["factor_id"],
            )
        )
    factors.sort(key=lambda f: ([int(x) for x in f["factor_id"].split(".")], f["factor_code"]))
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "ruleset_id": CUTOVER["before"],
        "status": "scaffold",
        "basis": BASIS_2014,
        "chapters": ["5", "6", "7", "8", "9"],
        "optional_items_policy": "any",
        "alias_map": {
            "status": "pending",
            "source": {"doc": "", "clause": "", "url": "", "fetched": ""},
            "map": {},
        },
        "foreword_deltas": [
            {
                "kind": item["kind"],
                "text": item["text"],
                "clauses": item["clauses"],
            }
            for item in TR.foreword_changes()
        ],
        "factors": factors,
    }


def _status_counts(ruleset_obj):
    counts = {"verified": 0, "pending": 0, "input_required": 0}
    for factor in ruleset_obj["factors"]:
        for status in _iter_statuses(factor):
            counts[status] = counts.get(status, 0) + 1
    return counts


def _iter_statuses(factor):
    yield factor["status"]
    yield factor["eligibility"]["status"]
    yield factor["period"]["status"]
    for disease in factor.get("target_diseases") or []:
        yield disease["status"]
    for key in ("pre_placement", "periodic", "post_placement", "emergency"):
        block = factor["examinations"][key]
        yield block["status"]
        for group in ("required_items", "supplementary_items", "optional_items"):
            for item in block.get(group) or []:
                yield item["status"]


def _build_manifest_obj(texts):
    entries = []
    for ruleset_id, filename in (
        (CUTOVER["before"], "ruleset-2014.json"),
        (CUTOVER["after"], "ruleset-2025.json"),
    ):
        data = texts[filename].encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        obj = ruleset_2014() if ruleset_id == CUTOVER["before"] else ruleset_2025()
        entries.append(
            {
                "ruleset_id": ruleset_id,
                "file": filename,
                "sha256": sha,
                "factor_count": len(obj["factors"]),
                "status_counts": _status_counts(obj),
            }
        )
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "generated_by": "tools/gen_rulesets.py",
        "note": (
            "M1 数据入库：2025 版第 5–7 章（化学/粉尘/物理）明细 verified；"
            "第 8–9 章（生物/特殊作业）仅因素身份 verified、明细 pending；"
            "2014 版为差异导向骨架（前言引述），未引述条目一律 pending。"
            "未挂原文核对的条目不得进入核查路径。"
        ),
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
    parsed = TR.transcribe()
    return {
        "ruleset-2025.json": dumps_stable(ruleset_2025(parsed)),
        "ruleset-2014.json": dumps_stable(ruleset_2014(parsed)),
    }


def build_outputs():
    """产出最终落盘映射（manifest 的 sha256 需在规则集写盘后计算）。"""
    return ruleset_texts()


def _pending_verifications():
    """待核对项（plan/06 §二 P-1–P-4）：未核对不得写入规则包，只在此登记并记渠道。

    M1 处置：P-1/P-2/P-3 在本机可及的官方渠道（gov.cn 政策文件库、国家标准全文公开
    系统、发布通告正文）均未取到**原文**，按纪律落 `pending` + 记录已查渠道，
    长任务继续推进（plan/06 纪律）。P-4 的分类目录附件可下载，但原文更新与否待核。
    """
    return [
        {
            "id": "P-1",
            "subject": "GBZ 188—2014 原发布文号与发布/实施日期",
            "status": "pending",
            "channels_checked": [
                "gov.cn 政策文件库（2025 年 9 项标准发布通告：只表述代替关系，未载 2014 版发布信息）",
                "国家标准全文公开系统 openstd.samr.gov.cn（GBZ 系列职业卫生标准未纳入该系统检索）",
                "本仓 GBZ 188—2025 官方 PDF 前言（只记『2014 年第一次修订』，无发布/实施日期）",
            ],
            "impact": "2014 版规则包 basis.effective_from 记 pending（不预填猜测值）；compare 通路不受影响。",
        },
        {
            "id": "P-2",
            "subject": "《中华人民共和国职业病防治法》现行修正次第与施行日期",
            "status": "pending",
            "channels_checked": ["gov.cn 政策文件库检索（未命中该书文本条目）"],
            "impact": "仅作背景依据引用，未写入任何规则条目的 source；不影响判定。",
        },
        {
            "id": "P-3",
            "subject": "《职业健康检查管理办法》令号与施行日期",
            "status": "pending",
            "channels_checked": ["gov.cn 政策文件库检索（未取到令号原文）"],
            "impact": "仅作背景依据引用，未写入任何规则条目的 source；不影响判定。",
        },
        {
            "id": "P-4",
            "subject": "国卫疾控发〔2015〕92 号（职业病危害因素分类目录）是否有后续更新",
            "status": "pending",
            "channels_checked": ["gov.cn / mem.gov.cn 转载页（确认文号与 2015-11-17 成文日期；更新情况未取到原文）"],
            "impact": "分类目录仅用于危害因素清单定位；规则包以 GBZ 188—2025 节次为准。",
        },
    ]


def _hanzi_count(text):
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def build_clauses_index(parsed):
    """依据索引（M1-2c）：每个已核对节次 → 标准号 + 节号 + URL + 抓取日期 + 快照 sha256。

    与规则包的分工（plan/05 §1.1 第 3 步）：规则包 basis 只到"标准号 + 节号"一层；
    本索引用以回答"这条依据出自哪份材料、该材料的字节指纹是什么"。
    """
    snapshot = TR.snapshot_path()
    with open(snapshot, "r", encoding="utf-8") as fh:
        raw = fh.read()
    snapshot_sha = file_sha256(snapshot)
    clauses = []
    for sid in sorted(parsed, key=lambda k: [int(x) for x in k.split(".")]):
        item = parsed[sid]
        clauses.append(
            {
                "clause": sid,
                "factor_id": sid,
                "factor_name": item["name"],
                "chapter": item["chapter"],
                "category": item["category"],
                "doc_code": BASIS_2025["doc_code"],
                "url": BASIS_2025["url"],
                "fetched": BASIS_2025["fetched"],
                "snapshot_sha256": snapshot_sha,
                "detail_verified": item["chapter"] in DETAIL_CHAPTERS,
                "sub_clauses": {
                    key: item["exams"][key]["basis_clause"]
                    for key in TR.EXAM_KEYS
                    if not item["exams"][key]["absent"]
                },
                "period_clause": item["period"]["clause"] or "",
            }
        )
    return {
        "schema_version": "1.0",
        "generated_by": "tools/gen_rulesets.py",
        "note": (
            "依据索引：规则包每个节次的出处、抓取日期与快照字节指纹。"
            "detail_verified=false 表示该节仅落因素身份、明细仍待核对。"
        ),
        "documents": [
            {
                "doc_code": BASIS_2025["doc_code"],
                "doc_title": BASIS_2025["doc_title"],
                "issuer": BASIS_2025["issuer"],
                "doc_number": BASIS_2025["doc_number"],
                "published": BASIS_2025["published"],
                "effective_from": BASIS_2025["effective_from"],
                "replaces": BASIS_2025["replaces"],
                "url": BASIS_2025["url"],
                "fetched": BASIS_2025["fetched"],
            },
            {
                "doc_code": BASIS_2014["doc_code"],
                "doc_title": BASIS_2014["doc_title"],
                "issuer": BASIS_2014.get("issuer", ""),
                "doc_number": "",
                "published": "",
                "effective_from": "",
                "effective_from_status": "pending",
                "replaces": "",
                "url": "",
                "fetched": BASIS_2014["fetched"],
                "note": "旧版已废止、官方全文预览下架；以 2025 版前言的差异引述为对照依据（决策 D-28）。",
            },
        ],
        "snapshots": [
            {
                "path": "data/knowledge/raw/GBZ188-2025.pdf",
                "sha256": file_sha256(
                    os.path.join(os.path.dirname(snapshot), "GBZ188-2025.pdf")
                ),
                "bytes": os.path.getsize(
                    os.path.join(os.path.dirname(snapshot), "GBZ188-2025.pdf")
                ),
                "note": "官方 PDF 原件快照（.gitattributes 标 -text，禁行尾归一化）。",
            },
            {
                "path": TR.SNAPSHOT_REL.replace(os.sep, "/"),
                "sha256": snapshot_sha,
                "bytes": os.path.getsize(snapshot),
                "hanzi_count": _hanzi_count(raw),
                "parsed_by": "pdftotext -enc UTF-8 -layout",
                "note": "PDF 解析文本快照；汉字数用于守门（零丢失）。",
            },
        ],
        "foreword_deltas": [
            {
                "kind": item["kind"],
                "text": item["text"],
                "clauses": item["clauses"],
            }
            for item in TR.foreword_changes()
        ],
        "pending_verifications": _pending_verifications(),
        "clauses": clauses,
    }


def _knowledge_dir():
    root = paths.find_data_dir()
    if root is None:
        print("错误：未找到 data/ 目录。")
        raise SystemExit(2)
    return os.path.join(root, "knowledge")


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

    # 依据索引（data/knowledge/clauses.json）：同一生成器产出，同一守门
    parsed = TR.transcribe()
    clauses_text = dumps_stable(build_clauses_index(parsed))

    # 自校验（schema）
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
        write_bytes_lf(os.path.join(_knowledge_dir(), "clauses.json"), clauses_text)
        print("已生成 data/rules/（%d 个文件）+ data/knowledge/clauses.json" % len(outputs))
        for rel in sorted(outputs):
            print("  %s  sha256=%s" % (rel, file_sha256(os.path.join(root, rel))[:16]))
        print(
            "  clauses.json  sha256=%s"
            % file_sha256(os.path.join(_knowledge_dir(), "clauses.json"))[:16]
        )
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
    clauses_path = os.path.join(_knowledge_dir(), "clauses.json")
    if not os.path.isfile(clauses_path):
        mismatch.append("knowledge/clauses.json（缺失）")
    else:
        with open(clauses_path, "rb") as fh:
            if fh.read().decode("utf-8") != clauses_text:
                mismatch.append("knowledge/clauses.json（内容不一致）")
    if mismatch:
        print("FROZEN_RULESETS_MISMATCH: %s" % "; ".join(mismatch))
        return 1
    print(
        "FROZEN_RULESETS_OK: %d 个规则包文件 + clauses.json 再生成逐字节一致"
        % len(outputs)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
