#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成监护档案与真值库生成器（**冻结产物唯一写入者**，决策 D-26 / plan/05 §二）。

产出 `data/truth/`：
    manifest.json            语料库元数据 + **算例覆盖矩阵** + **不可达算例声明**
    records/<record_id>.json 合成监护档案（内嵌 `expect` 植入真值）
    truth.json               聚合真值库（由同一源派生，杜绝双份漂移）

为什么需要真值库（plan/05 §2.4）：M2 起引擎要用**独立实现路径**对账——
真值由本脚本按"算例语义"独立算出（**不调引擎**），引擎若与真值不符即为缺陷。

纪律：
  * 禁 stdlib `random`（不承诺跨版本序列一致）→ 自研 **splitmix64**；
  * 禁 set 迭代序 → 一律排序后迭代；
  * 禁系统时钟进产物 → 无时间戳，生成参数由固定 seed / 显式常量给出；
  * 落盘 write_bytes + 显式 LF；`--check` 再生成逐字节一致；
  * 虚构人员/企业（白名单命名），**不含任何真实劳动者信息**（plan/05 §2.2）。

用法：
    py -3.8 tools/gen_synthetic.py            # 生成
    py -3.8 tools/gen_synthetic.py --check    # 再生成并断言逐字节一致
"""

from __future__ import annotations

import calendar
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

from ohscheck import paths  # noqa: E402
from ohscheck.loaders import dumps_stable, load_path, write_bytes_lf  # noqa: E402
from ohscheck.rules.loader import file_sha256  # noqa: E402

# ---- 生成参数（固定，进产物；禁系统时钟）----
SEED = 20261014
CORPUS_ID = "SYN-TRUTH-M1"
RULESET_ID = "GBZ188-2025"

# ---- 白名单命名（plan/05 §2.2：虚构姓名代号 + 测试号段）----
EMPLOYER_NAME = "示例制造（合成）有限公司"
EMPLOYER_ID = "90000000000000SYN"
ID_PREFIX = "90000000"
ID_SUFFIX = "SYN"


def employee_name(seq):
    return "示例人员 A-%03d" % seq


def employee_id(seq):
    return "%s%03d%s" % (ID_PREFIX, seq, ID_SUFFIX)


def position_id(name_slug):
    return "SYN-POS-%s" % name_slug


# ---- 算例 → 真实危害因素（只用生产规则包里已核对的第 5–7 章因素）----
CASE_FACTORS = {
    "benzene": {"factor_code": "GBZ188-5.19", "position": "苯罐区操作岗"},
    "lead": {"factor_code": "GBZ188-5.1", "position": "铅蓄电池装配岗"},
    "noise": {"factor_code": "GBZ188-7.1", "position": "冲压车间操作岗"},
    "heat": {"factor_code": "GBZ188-7.3", "position": "熔炼炉前作业岗"},
    "dust_metal": {"factor_code": "GBZ188-6.7", "position": "金属打磨作业岗"},
    "laser": {"factor_code": "GBZ188-7.8", "position": "激光切割作业岗"},
    "acid": {"factor_code": "GBZ188-5.55", "position": "酸洗作业岗"},
}


# ---------------- splitmix64（自研确定性 PRNG）----------------


class SplitMix64:
    """splitmix64：跨版本位级确定的伪随机序列（替代 stdlib random）。"""

    __slots__ = ("state",)

    MASK = (1 << 64) - 1

    def __init__(self, seed):
        self.state = seed & self.MASK

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & self.MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.MASK
        return z ^ (z >> 31)

    def below(self, n):
        """[0, n) 上的确定性取值（拒绝采样，避免取模偏差）。"""
        if n <= 0:
            raise ValueError("n 必须为正")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            v = self.next_u64()
            if v < limit:
                return v % n

    def choice(self, seq):
        items = sorted(seq)  # 禁 set 迭代序：先排序再取
        return items[self.below(len(items))]


# ---------------- 独立参考实现（**不调引擎**，plan/05 §2.4）----------------


def _ref_add_months(iso, months):
    """独立参考的日历月加法（月末夹取）——与 engine/period.py 分头实现，用于对账。"""
    year, month, day = (int(x) for x in iso.split("-"))
    total = month - 1 + months
    ny = year + total // 12
    nm = total % 12 + 1
    last = calendar.monthrange(ny, nm)[1]
    return "%04d-%02d-%02d" % (ny, nm, min(day, last))


def ref_period(months, last, current):
    """独立参考的周期判定（due 计入合规；无基线不报超期）。"""
    if months is None:
        return "input_required"
    if last is None:
        return "no_baseline"
    due = _ref_add_months(last, months)
    if current < due:
        return "compliant"
    if current == due:
        return "due"
    return "overdue"


def ref_verdict(expected, provided, period_verdict, exam_type):
    """独立参考的定级（plan/04 §3.2 边界）。"""
    missing = sorted(set(expected) - set(provided))
    period_bad = exam_type == "periodic" and period_verdict == "overdue"
    if not expected:
        return ("partial" if period_bad else "compliant"), missing
    if not missing:
        return ("partial" if period_bad else "compliant"), missing
    if set(expected).issubset(set(missing)):
        return "non_compliant", missing
    return "partial", missing


# ---------------- 规则包读取（真值来源）----------------


def _load_ruleset():
    root = paths.find_data_dir()
    if root is None:
        print("错误：未找到 data/ 目录。")
        raise SystemExit(2)
    path = os.path.join(root, "rules", "ruleset-2025.json")
    return load_path(path), path


def _required_items(ruleset_obj, factor_code, exam_type):
    for factor in ruleset_obj["factors"]:
        if factor["factor_code"] == factor_code:
            block = factor["examinations"][exam_type]
            return [i["item_code"] for i in block["required_items"]]
    raise KeyError(factor_code)


def _period_months(ruleset_obj, factor_code):
    for factor in ruleset_obj["factors"]:
        if factor["factor_code"] == factor_code:
            period = factor["period"]
            if period.get("kind") == "months":
                return period["value"]
            return None
    raise KeyError(factor_code)


# ---------------- 档案构造 ----------------


class RecordSpec:
    """一条算例的声明（语义层）→ 由生成器算成档案 + 植入真值。"""

    __slots__ = (
        "slug", "seq", "case_key", "exam_type", "exam_date", "last_exam_date",
        "provided", "extra_items", "coverage", "note", "should_be_clean",
    )

    def __init__(self, slug, seq, case_key, exam_type, exam_date,
                 provided="all", last_exam_date=None, extra_items=(),
                 coverage="", note="", should_be_clean=False):
        self.slug = slug
        self.seq = seq
        self.case_key = case_key
        self.exam_type = exam_type
        self.exam_date = exam_date
        self.provided = provided
        self.last_exam_date = last_exam_date
        self.extra_items = tuple(extra_items)
        self.coverage = coverage
        self.note = note
        self.should_be_clean = should_be_clean


def _materialize(spec, ruleset_obj):
    """把声明算成 (record_dict, truth_dict)。"""
    case = CASE_FACTORS[spec.case_key]
    factor_code = case["factor_code"]
    required = _required_items(ruleset_obj, factor_code, spec.exam_type)
    months = _period_months(ruleset_obj, factor_code)

    if spec.provided == "all":
        provided = list(required)
    elif spec.provided == "none":
        provided = []
    elif isinstance(spec.provided, str) and spec.provided.startswith("all_but:"):
        drop = spec.provided.split(":", 1)[1]
        provided = [c for c in required if c != drop]
    elif isinstance(spec.provided, (list, tuple)):
        provided = list(spec.provided)
    else:
        raise ValueError("未知 provided 声明：%r" % (spec.provided,))
    provided = provided + list(spec.extra_items)

    record_id = "SYN-TRUTH-%03d" % spec.seq
    record = {
        "record_id": record_id,
        "employee_id": employee_id(spec.seq),
        "employee_name": employee_name(spec.seq),
        "position_id": position_id(spec.slug),
        "factor_code": factor_code,
        "exam_date": spec.exam_date,
        "exam_type": spec.exam_type,
        "items": provided,
        "conclusion_code": "normal",
        "notified_suspected": False,
    }
    if spec.last_exam_date:
        record["last_exam_date"] = spec.last_exam_date

    period_verdict = (
        ref_period(months, spec.last_exam_date, spec.exam_date)
        if spec.exam_type == "periodic"
        else "not_applicable"
    )
    verdict, missing = ref_verdict(required, provided, period_verdict, spec.exam_type)
    expect = {
        "verdict": verdict,
        "missing_items": missing,
        "period_verdict": period_verdict,
        "expected_items": sorted(required),
    }
    if spec.should_be_clean:
        expect["should_be_clean"] = True
    unwrapped = [x for x in spec.extra_items]
    if unwrapped:
        expect["also_expect"] = [{"kind": "warning", "item_code": x} for x in unwrapped]
    truth = {
        "record_id": record_id,
        "factor_code": factor_code,
        "case": spec.case_key,
        "coverage": spec.coverage,
        "note": spec.note,
        "expect": expect,
    }
    record["expect"] = expect
    record["expect_case"] = spec.case_key
    return record, truth


def build_specs():
    """算例清单（对照 plan/05 §2.3 算例覆盖矩阵逐行）。"""
    specs = []
    n = [0]

    def add(slug, case_key, exam_type, exam_date, **kwargs):
        n[0] += 1
        specs.append(
            RecordSpec(slug=slug, seq=n[0], case_key=case_key,
                       exam_type=exam_type, exam_date=exam_date, **kwargs)
        )

    # --- 化学因素：苯（GBZ188-5.19，周期 12 个月）---
    add("benzene", "benzene", "periodic", "2026-09-15",
        last_exam_date="2025-10-01", coverage="化学因素/苯 · 应检项集合",
        note="应检项齐备、周期未到 → 符合（应零命中）", should_be_clean=True)
    add("benzene", "benzene", "pre_placement", "2026-09-15",
        coverage="化学因素/苯 · 上岗前应检项集合",
        note="上岗前应检项齐备 → 符合（应零命中）", should_be_clean=True)

    # --- 化学因素：铅（GBZ188-5.1，周期按血铅/尿铅分档 → input_required）---
    add("lead", "lead", "pre_placement", "2026-09-15",
        coverage="化学因素/铅 · 应检项集合",
        note="上岗前应检项齐备 → 符合（应零命中）", should_be_clean=True)
    add("lead", "lead", "post_placement", "2026-09-15",
        coverage="化学因素/铅 · 离岗时『同 5.1.2.2』引用解析",
        note="离岗时内容经条文引用解析后齐备 → 符合（验证『同 X.Y.Z』通路）",
        should_be_clean=True)

    # --- 物理因素：噪声（GBZ188-7.1，周期按等效声级分档 → input_required）---
    add("noise", "noise", "pre_placement", "2026-09-20",
        coverage="物理因素/噪声 · 应检项集合",
        note="上岗前应检项齐备 → 符合（应零命中）", should_be_clean=True)
    add("noise", "noise", "periodic", "2026-09-20", last_exam_date="2025-09-20",
        coverage="物理因素/噪声 · 周期不承载单值时仍按项目构成判定",
        note="周期按分级分档（input_required）不参与超期判定；项目齐备 → 符合",
        should_be_clean=True)

    # --- 物理因素：高温（GBZ188-7.3，周期 12 个月）---
    add("heat", "heat", "periodic", "2026-09-20", last_exam_date="2025-09-20",
        coverage="物理因素/高温 · 应检项集合 + 周期恰好到期",
        note="应检项齐备且周期恰好到期（due 计入合规）→ 符合", should_be_clean=True)

    # --- 缺项：缺某必检项目 ---
    add("benzene", "benzene", "periodic", "2026-09-15",
        provided="all_but:肝功能", last_exam_date="2025-10-01",
        coverage="缺项 · 缺某一必检项目",
        note="缺 1 项必检项 → partial，缺项集合含『肝功能』")
    add("lead", "lead", "post_placement", "2026-09-15",
        provided="all_but:血铅和/或尿铅",
        coverage="缺项 · 缺某一必检项目（离岗时）",
        note="离岗时缺 1 项 → partial")

    # --- 缺项：必检项全缺 ---
    add("benzene", "benzene", "periodic", "2026-09-15",
        provided="none", last_exam_date="2025-10-01",
        coverage="缺项 · 必检项全缺",
        note="必检项一项未做 → non_compliant，缺项集合 = 应检项全集")

    # --- 缺项：缺离岗时检查（以离岗时档案缺项表达）---
    add("noise", "noise", "post_placement", "2026-09-20",
        provided="none",
        coverage="缺项 · 缺离岗时检查",
        note="离岗时检查必检项全缺 → non_compliant")

    # --- 周期边界：差一天 / 恰好到期 / 超一天 ---
    add("benzene", "benzene", "periodic", "2026-09-14",
        last_exam_date="2025-09-15", coverage="周期边界 · 差一天到期",
        note="到期前一日 → compliant（应零命中）", should_be_clean=True)
    add("benzene", "benzene", "periodic", "2026-09-15",
        last_exam_date="2025-09-15", coverage="周期边界 · 恰好到期",
        note="到期当日 → due，计入合规（应零命中）", should_be_clean=True)
    add("benzene", "benzene", "periodic", "2026-09-16",
        last_exam_date="2025-09-15", coverage="周期边界 · 超一天",
        note="到期后一日 → overdue → partial（计入不符合）")

    # --- 周期边界：月末夹取（闰年 2 月 29 日 + 12 月 → 平年 2 月 28 日）---
    # 体检日必须落在 2025 版适用期（>= 切口日）才能命中 2025 规则包（版本锚定按体检日）；
    # 故取 2029（平年）到期日：上次 2028-02-29（闰年）+ 12 月 → 夹取为 2029-02-28。
    add("benzene", "benzene", "periodic", "2029-02-28",
        last_exam_date="2028-02-29", coverage="周期边界 · 月末夹取（闰转平）",
        note="上次 2028-02-29（闰年）+ 12 月 → 夹取为 2029-02-28（平年），当日检查 → due（合规）",
        should_be_clean=True)

    # --- 周期（其他月份数：24 / 36）---
    add("dust_metal", "dust_metal", "periodic", "2026-09-20",
        last_exam_date="2024-09-20", coverage="周期边界 · 24 个月周期到期",
        note="24 个月周期恰好到期 → due（合规）", should_be_clean=True)
    add("laser", "laser", "periodic", "2026-09-20",
        last_exam_date="2023-09-20", coverage="周期边界 · 36 个月周期到期",
        note="36 个月周期恰好到期 → due（合规）", should_be_clean=True)
    add("dust_metal", "dust_metal", "periodic", "2026-09-21",
        last_exam_date="2024-09-20", coverage="周期边界 · 24 个月超一天",
        note="超一天 → overdue → partial")

    # --- 无基线（首次检查）---
    add("benzene", "benzene", "periodic", "2026-09-15",
        coverage="周期边界 · 首次检查无基线",
        note="无上次检查记录 → no_baseline，不报超期（应零命中）", should_be_clean=True)

    # --- 别名降级（应零 fail，允许 warning）---
    add("acid", "acid", "periodic", "2026-09-20",
        extra_items=["某种别名的检查项目写法"], last_exam_date="2025-09-20",
        coverage="别名降级 · 归一不成立只报 warning",
        note="齐备 + 一个非规范写法项目 → compliant，该写法记 unmapped（降级 warning 不判缺失）",
        should_be_clean=True)

    return specs


def build_bulk(ruleset_obj, start_seq):
    """确定性批量队列（splitmix64 驱动）：验证引擎在规模下的稳定性与可复现。

    真值同样由**独立参考实现**算出；批量件只覆盖"项目构成 + 周期"两个可判定维度。
    """
    rng = SplitMix64(SEED)
    cases = sorted(CASE_FACTORS)
    exam_types = ("pre_placement", "periodic", "post_placement")
    # 体检日必须落在 2025 版适用期（>= 切口日）→ 用 2026 起的月份，
    # 否则版本锚定会（正确地）切到 2014 版，与本语料的 ruleset_id 不符。
    exam_dates = ["2026-%02d-%02d" % (m, d) for m in range(9, 13) for d in (10, 20)]
    lookup_offsets = (6, 12, 18, 24, 30, 36, 42)
    records = []
    truths = []
    for i in range(48):
        case_key = cases[rng.below(len(cases))]
        exam_type = exam_types[rng.below(len(exam_types))]
        case = CASE_FACTORS[case_key]
        factor_code = case["factor_code"]
        required = _required_items(ruleset_obj, factor_code, exam_type)
        # 随机决定"做了几项"（从全齐到全缺）
        keep = rng.below(len(required) + 1)
        provided = sorted(required)[:keep]
        exam_date = exam_dates[rng.below(len(exam_dates))]
        last = None
        if exam_type == "periodic":
            back = lookup_offsets[rng.below(len(lookup_offsets))]
            y = int(exam_date[:4])
            m = int(exam_date[5:7]) - (back % 12)
            y -= back // 12
            while m <= 0:
                m += 12
                y -= 1
            d = min(int(exam_date[8:10]), 28)
            last = "%04d-%02d-%02d" % (y, m, d)
        seq = start_seq + i
        spec = RecordSpec(
            slug=case_key, seq=seq, case_key=case_key, exam_type=exam_type,
            exam_date=exam_date, provided=provided, last_exam_date=last,
            coverage="批量队列 · 项目构成/周期可判定性",
            note="批量确定性件（splitmix64 驱动）",
        )
        record, truth = _materialize(spec, ruleset_obj)
        records.append(record)
        truths.append(truth)
    return records, truths


# ---------------- 覆盖矩阵与不可达声明（如实留档）----------------

COVERAGE_MATRIX = [
    ("化学因素 · 苯作业人员应检项集合", ["SYN-TRUTH-001", "SYN-TRUTH-002"],
     "GBZ188-5.19（周期 12 个月，四时点项目一致）"),
    ("化学因素 · 铅及其无机化合物作业人员应检项集合", ["SYN-TRUTH-003", "SYN-TRUTH-004"],
     "GBZ188-5.1；离岗时经『同 5.1.2.2』条文引用解析"),
    ("物理因素 · 噪声作业人员应检项集合", ["SYN-TRUTH-005", "SYN-TRUTH-006"],
     "GBZ188-7.1；周期按等效声级分档 → input_required，不参与超期判定"),
    ("物理因素 · 高温作业人员应检项集合", ["SYN-TRUTH-007"],
     "GBZ188-7.3（周期 12 个月）"),
    ("缺项 · 缺离岗时检查", ["SYN-TRUTH-010"], "离岗时必检项全缺 → non_compliant"),
    ("缺项 · 缺某一必检项目", ["SYN-TRUTH-008", "SYN-TRUTH-009"],
     "缺 1 项 → partial，missing_items 精确到项"),
    ("缺项 · 必检项全缺", ["SYN-TRUTH-010", "SYN-TRUTH-011"], "expected ⊆ missing → non_compliant"),
    ("周期边界 · 恰好到期（current == due）", ["SYN-TRUTH-013", "SYN-TRUTH-007", "SYN-TRUTH-016", "SYN-TRUTH-017"],
     "due 当日计入合规（period_verdict=due，verdict=compliant）"),
    ("周期边界 · 差一天到期 / 超一天", ["SYN-TRUTH-012", "SYN-TRUTH-014", "SYN-TRUTH-018"],
     "差一天 compliant；超一天 overdue → partial"),
    ("周期边界 · 月末夹取（1/31+1 月口径 → 闰转平）",
     ["SYN-TRUTH-015"],
     "上次 2024-02-29 + 12 月夹取为 2025-02-28；engine/period.add_months 另配单元测试"),
    ("周期边界 · 首次检查无基线", ["SYN-TRUTH-019"], "no_baseline，不报超期"),
    ("别名降级 · 项目名用别名写法", ["SYN-TRUTH-020"],
     "归一不成立 → unmapped + warning，不判缺失（决策 D-17）；should_be_clean=true"),
    ("误报对照 · 应检项齐备 + 周期合规（应零命中）",
     ["SYN-TRUTH-001", "SYN-TRUTH-002", "SYN-TRUTH-003", "SYN-TRUTH-004", "SYN-TRUTH-005",
      "SYN-TRUTH-006", "SYN-TRUTH-007", "SYN-TRUTH-012", "SYN-TRUTH-013", "SYN-TRUTH-015",
      "SYN-TRUTH-016", "SYN-TRUTH-017", "SYN-TRUTH-019", "SYN-TRUTH-020"],
     "should_be_clean=true 显式声明（M1-5）；基准/引擎层**只读**该声明，不自选考卷"),
    ("干净但降级 · 别名可映射的齐备档案", ["SYN-TRUTH-020"],
     "应零 fail，允许 warning（与上一条共用同一件，语义为「降级但不判缺」）"),
    ("批量队列 · 项目构成 / 周期可判定性", ["SYN-TRUTH-021 … SYN-TRUTH-068"],
     "splitmix64 驱动 48 件，全量可复现"),
]

# 不可达算例声明（诚实纪律：规则包的真实结构使其不可达，必须写出原因，不得假装覆盖）
UNREACHABLE_CASES = [
    {
        "case": "不适用 · 危害因素不适用该人员（verdict=not_applicable）",
        "reason": (
            "标准通过『第 4.5 节 职业健康监护人群的界定原则』对**所列危害因素**定义监护人群——"
            "接触即纳入，逐因素不设接触水平阈值。故生产规则包第 5–7 章全部因素的适用性为 "
            "kind=always，not_applicable 在真实规则包上**不可达**。"
        ),
        "covered_by": (
            "机制层：data/benchmark/ 的合成夹具含 kind=threshold 因素，覆盖 not_applicable 与 "
            "input_required 两条分支（基准验机制、不验国标内容，决策 D-51）。"
        ),
    },
    {
        "case": "版本差异 · 同一岗位在 2014/2025 两版下应检项不同",
        "reason": (
            "GBZ 188—2014 官方全文不可得（已废止、预览下架），2014 版规则包是**差异导向骨架**"
            "（决策 D-28）——其项目明细全为 pending，引用到即被门控拦截。"
            "故**档案级**的跨版本应检差异在真实规则包上不可达。"
        ),
        "covered_by": (
            "结构层：`ohscheck compare` 在两版间报因素新增/删除差异（GBZ188-5.58 等 19 个新增、"
            "甲苯二异氰酸酯/结核病/肝炎病防治作业 3 个删除），已由 manifest.foreword_deltas 承载；"
            "机制层：data/benchmark/ 覆盖同因素两版条目构成差异。"
        ),
    },
]


def build_manifest(ruleset_obj, ruleset_path, records, truths):
    return {
        "schema_version": "1.0",
        "corpus_id": CORPUS_ID,
        "generated_by": "tools/gen_synthetic.py",
        "synthetic": True,
        "seed": SEED,
        "ruleset_id": RULESET_ID,
        "ruleset_sha256": file_sha256(ruleset_path),
        "record_count": len(records),
        "clean_count": sum(1 for t in truths if t["expect"].get("should_be_clean")),
        "coverage_matrix": [
            {"case": case, "records": recs, "note": note}
            for case, recs, note in COVERAGE_MATRIX
        ],
        "unreachable_cases": UNREACHABLE_CASES,
        "naming_policy": {
            "employees": "示例人员 A-<序号>",
            "identity_numbers": "%s…%s（保留测试号段）" % (ID_PREFIX, ID_SUFFIX),
            "employer": EMPLOYER_NAME,
            "note": "全部为虚构实体；不含任何真实劳动者信息（plan/05 §2.2）。",
        },
        "sensitive_note": (
            "健康信息属敏感个人信息：本语料仅含结构化字段"
            "（岗位危害因素/体检日期/检查时点/实检项目代码/结论代码），"
            "不构造任何真实医学指标、影像或诊断文字。"
        ),
        "private_dir_note": (
            "data/truth/_private/ 为本地不入仓目录（.gitignore 已排除）："
            "如需在本机保留带真实来源线索的中间样本，放该目录，且**不得**进入语料库产物。"
        ),
    }


def build_outputs():
    ruleset_obj, ruleset_path = _load_ruleset()
    specs = build_specs()
    records = []
    truths = []
    for spec in specs:
        record, truth = _materialize(spec, ruleset_obj)
        records.append(record)
        truths.append(truth)
    bulk_records, bulk_truths = build_bulk(ruleset_obj, start_seq=len(records) + 1)
    records.extend(bulk_records)
    truths.extend(bulk_truths)

    outputs = {}
    for record in records:
        outputs["records/%s.json" % record["record_id"]] = dumps_stable(record)
    truth_lib = {
        "corpus_id": CORPUS_ID,
        "ruleset_id": RULESET_ID,
        "seed": SEED,
        "entries": truths,
    }
    outputs["truth.json"] = dumps_stable(truth_lib)
    outputs["manifest.json"] = dumps_stable(
        build_manifest(ruleset_obj, ruleset_path, records, truths)
    )
    return outputs


def truth_dir():
    root = paths.find_data_dir()
    if root is None:
        print("错误：未找到 data/ 目录。")
        raise SystemExit(2)
    return os.path.join(root, "truth")


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
    root = truth_dir()
    outputs = build_outputs()

    if not check:
        for rel, text in sorted(outputs.items()):
            write_bytes_lf(os.path.join(root, rel.replace("/", os.sep)), text)
        print("已生成 data/truth/（%d 个文件）" % len(outputs))
        for rel in sorted(outputs)[:6]:
            path = os.path.join(root, rel.replace("/", os.sep))
            print("  %s  sha256=%s" % (rel, file_sha256(path)[:16]))
        print("  …（共 %d 个文件）" % len(outputs))
        return 0

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
        print("FROZEN_TRUTH_MISMATCH: %s" % "; ".join(mismatch[:8]))
        return 1
    print("FROZEN_TRUTH_OK: %d 个文件再生成逐字节一致" % len(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
