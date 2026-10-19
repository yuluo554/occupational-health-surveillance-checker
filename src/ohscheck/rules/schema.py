"""规则包 schema 校验。

不变式（plan/03 §4.4，测试硬断言）：
    status == verified      ⇒ source.doc / source.clause 非空，且承载的值非 null
    status == pending       ⇒ 承载的值为 null（不许"半核对"的悬空值）
    status == input_required⇒ basis 非空（说明为何不承载）

校验在载入时执行；违反即 InputError（退出码 2），绝不"宽容放行"。
"""

from __future__ import annotations

import re

from ..errors import InputError

STATUSES = ("verified", "pending", "input_required")
# 规则包**顶层** `status`：整包完成度标签，**不参与门控**（判定只看条目级三态）。
#   现行版 = "partial"（第 5–7 章明细已核对，第 8–9 章明细 pending）
#   旧版   = "scaffold"（差异导向骨架）
# 取值收在本元组里由 schema 校验；字段本身**可选**（合成夹具不带该字段）。
PACKAGE_STATUSES = ("partial", "scaffold")
# 危害因素类别：与 GBZ 一八八最新版的章节划分对齐（第 5–9 章）。
#   5 接触有害化学因素 → chemical
#   6 粉尘             → dust
#   7 接触有害物理因素 → physical
#   8 接触有害生物因素 → biological
#   9 特殊作业人员     → special
FACTOR_CATEGORIES = ("chemical", "physical", "dust", "biological", "special")
EXAM_TYPE_KEYS = ("pre_placement", "periodic", "post_placement", "emergency")
ELIGIBILITY_KINDS = ("always", "threshold", "input_required", "pending")
PERIOD_KINDS = ("months", "none", "input_required", "pending")
# 选检项目口径由**数据**声明，不在代码里按版本号硬编码：
#   any            = 各时点均可有选检项
#   emergency_only = 仅应急检查保留选检项（新标口径：删除上岗前/在岗期间/离岗时选检项）
OPTIONAL_ITEMS_POLICIES = ("any", "emergency_only")

SCHEMA_VERSION = "1.0"

# 合成夹具（基准/测试用）的出处标记前缀。
# 硬不变式：标 synthetic 的规则集，其任何 source.doc 都**不得**是真实标准号——
# 从结构上杜绝"合成夹具冒充国标出处"（数据纪律，plan/02 §4.4）。
SYNTHETIC_MARKER = "SYNTHETIC-"

# 承载"值"的字段名 → 是否允许 null
_VALUE_FIELDS = ("value", "threshold")

_CLAUSE_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")


def _fail(msg):
    raise InputError("规则包 schema 校验失败：%s" % msg)


def _require_synthetic_provenance(src, where):
    """合成规则集的 source.doc 必须带合成标记，且不得含真实标准号形态。"""
    doc = str(src.get("doc") or "")
    if not doc.startswith(SYNTHETIC_MARKER):
        _fail(
            "%s 属合成夹具，source.doc 必须以 %r 开头（实际 %r）——"
            "合成数据不得冒充真实标准出处" % (where, SYNTHETIC_MARKER, doc)
        )


def _check_source(src, where):
    if not isinstance(src, dict):
        _fail("%s.source 必须是对象" % where)
    for key in ("doc", "clause", "url", "fetched"):
        if key not in src:
            _fail("%s.source 缺少字段 %r" % (where, key))


def _check_status_block(block, where, value_field=None, synthetic=False, value_required=None):
    """校验一个挂 status 的块。

    Args:
        value_field: 承载"值"的字段名（如 threshold / value）。
        value_required: 该字段在 verified 时是否必须有值。
            None = 由 status 决定（verified 必须有值）；
            False = 本块按 kind 语义**不承载值**（如 kind=always 无阈值、
            kind=none 无周期月数），verified 时 null 是正确形态。
    """
    if not isinstance(block, dict):
        _fail("%s 必须是对象" % where)
    status = block.get("status")
    if status not in STATUSES:
        _fail("%s.status %r 非法（合法值：%s）" % (where, status, ", ".join(STATUSES)))

    if value_required is None:
        value_required = value_field is not None

    if status == "verified":
        src = block.get("source")
        _check_source(src, where)
        if synthetic:
            _require_synthetic_provenance(src, where)
        if not str(src.get("doc") or "").strip():
            _fail("%s 已标 verified 但 source.doc 为空——未挂原文核对不得标 verified" % where)
        if not str(src.get("clause") or "").strip():
            _fail("%s 已标 verified 但 source.clause 为空" % where)
        if value_required and block.get(value_field) is None:
            _fail("%s 已标 verified 但 %s 为 null（不许半核对的悬空值）" % (where, value_field))
    elif status == "pending":
        if value_required and block.get(value_field) is not None:
            _fail(
                "%s 标 pending 却已填 %s——pending 一律为 null，防止'先填大概值再标待核对'"
                % (where, value_field)
            )
    elif status == "input_required":
        if not str(block.get("basis") or "").strip():
            _fail("%s 标 input_required 但 basis 为空——须说明为何本不由规则包承载" % where)
    return status


def _validate_item(item, where, synthetic=False):
    if not isinstance(item, dict):
        _fail("%s 必须是对象" % where)
    for key in ("item_code", "item_name"):
        if key not in item:
            _fail("%s 缺少字段 %r" % (where, key))
    _check_status_block(item, where, value_field=None, synthetic=synthetic)
    if item.get("status") == "verified" and not str(item.get("item_code") or "").strip():
        _fail("%s 已标 verified 但 item_code 为空" % where)


def _validate_exam_block(block, where, key, optional_policy=None, synthetic=False):
    if not isinstance(block, dict):
        _fail("%s 必须是对象" % where)
    for group in ("required_items", "supplementary_items", "optional_items"):
        if not isinstance(block.get(group), list):
            _fail("%s.%s 必须是数组" % (where, group))
    for group in ("required_items", "supplementary_items", "optional_items"):
        for idx, item in enumerate(block.get(group) or []):
            _validate_item(item, "%s.%s[%d]" % (where, group, idx), synthetic)

    _check_status_block(block, where, value_field=None, synthetic=synthetic)

    # 选检项目口径由**规则包数据**声明（optional_items_policy），不在这里按版本号硬编码。
    # "emergency_only" = 仅应急检查保留选检项（新标口径）。
    if optional_policy == "emergency_only" and key != "emergency":
        if block.get("optional_items"):
            _fail(
                "%s 在本规则集口径（optional_items_policy=emergency_only）下"
                "不得有选检项目：仅应急检查保留选检项" % where
            )


def _validate_factor(factor, idx, optional_policy, synthetic=False):
    where = "factors[%d]" % idx
    if not isinstance(factor, dict):
        _fail("%s 必须是对象" % where)
    for key in ("factor_id", "factor_code", "factor_name", "chapter", "category"):
        if not str(factor.get(key) or "").strip():
            _fail("%s 缺少非空字段 %r" % (where, key))
    if factor["category"] not in FACTOR_CATEGORIES:
        _fail("%s.category %r 非法" % (where, factor["category"]))
    if not _CLAUSE_RE.match(str(factor["factor_id"])):
        _fail("%s.factor_id %r 不是合法节号（如 5.1.0）" % (where, factor["factor_id"]))

    elig = factor.get("eligibility")
    if not isinstance(elig, dict):
        _fail("%s.eligibility 必须是对象" % where)
    if elig.get("kind") not in ELIGIBILITY_KINDS:
        _fail("%s.eligibility.kind %r 非法" % (where, elig.get("kind")))
    # 阈值语义：kind=threshold 必带 comparator 与 unit；其余 kind 不承载阈值
    elig_kind = elig.get("kind")
    if elig_kind == "threshold":
        if not str(elig.get("comparator") or "").strip():
            _fail("%s.eligibility 为 threshold 但 comparator 为空" % where)
        if not str(elig.get("unit") or "").strip():
            _fail("%s.eligibility 为 threshold 但 unit 为空" % where)
    _check_status_block(
        elig,
        "%s.eligibility" % where,
        value_field="threshold",
        synthetic=synthetic,
        # kind=always 无阈值；threshold 必须有值；input_required/pending 不承载确定值
        value_required=(elig_kind == "threshold"),
    )

    for di, disease in enumerate(factor.get("target_diseases") or []):
        _check_status_block(
            disease, "%s.target_diseases[%d]" % (where, di), value_field="name",
            synthetic=synthetic,
        )

    exams = factor.get("examinations")
    if not isinstance(exams, dict):
        _fail("%s.examinations 必须是对象" % where)
    for key in EXAM_TYPE_KEYS:
        if key not in exams:
            _fail("%s.examinations 缺少时点 %r" % (where, key))
        _validate_exam_block(
            exams[key], "%s.examinations.%s" % (where, key), key, optional_policy, synthetic
        )

    period = factor.get("period")
    if not isinstance(period, dict):
        _fail("%s.period 必须是对象" % where)
    period_kind = period.get("kind")
    if period_kind not in PERIOD_KINDS:
        _fail("%s.period.kind %r 非法" % (where, period_kind))
    # 值语义与 kind 对齐：months 必须有正整数月数；其余 kind 不承载值
    if period_kind == "months":
        value = period.get("value")
        if not isinstance(value, int) or value <= 0:
            _fail("%s.period.value 必须是正整数月数" % where)
    _check_status_block(
        period,
        "%s.period" % where,
        value_field="value",
        synthetic=synthetic,
        value_required=(period_kind == "months"),
    )

    _check_status_block(factor, where, value_field=None, synthetic=synthetic)


def validate_ruleset(obj):
    """校验整份规则集。通过返回 obj，失败抛 InputError。"""
    if not isinstance(obj, dict):
        _fail("规则集根必须是对象")
    if obj.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version 必须是 %r，实际 %r" % (SCHEMA_VERSION, obj.get("schema_version")))

    synthetic = bool(obj.get("synthetic"))

    ruleset_id = obj.get("ruleset_id")
    if not str(ruleset_id or "").strip():
        _fail("缺少 ruleset_id")

    # 顶层 status = 整包完成度标签（**不参与门控**）：可选，但出现时必须在合法集内。
    # 门控只消费条目级 `verified`/`pending`/`input_required`（STATUSES）。
    if "status" in obj and obj["status"] not in PACKAGE_STATUSES:
        _fail(
            "顶层 status %r 非法（整包完成度标签，合法值：%s；注意它不参与门控）"
            % (obj.get("status"), ", ".join(PACKAGE_STATUSES))
        )

    basis = obj.get("basis")
    if not isinstance(basis, dict):
        _fail("缺少 basis 对象")
    for key in ("doc_code", "doc_title"):
        if not str(basis.get(key) or "").strip():
            _fail("basis 缺少非空字段 %r" % key)
    # effective_from：默认必须非空；但**已核对但确实查不到**的情况下，允许以
    # `effective_from_status: pending` 显式声明"该日期是待核对项"——
    # 这正是"未核对不得编造"的结构化表达（决策 D-13 同族：未核对 ≠ 取个默认值）。
    # 反之，标了 pending 却填了日期 → 拒绝（防止"先填个大概值再标待核对"）。
    eff_status = basis.get("effective_from_status", "verified")
    if eff_status not in STATUSES:
        _fail("basis.effective_from_status %r 非法（合法值：%s）"
              % (eff_status, ", ".join(STATUSES)))
    if eff_status == "pending":
        if str(basis.get("effective_from") or "").strip():
            _fail("basis.effective_from_status 标 pending 却已填 effective_from——"
                  "待核对的日期不得预填")
    elif not str(basis.get("effective_from") or "").strip():
        _fail("basis 缺少非空字段 'effective_from'")
    if synthetic:
        # 合成夹具的三道结构护栏（数据纪律，plan/02 §4.4）
        if not str(basis.get("doc_code") or "").startswith(SYNTHETIC_MARKER):
            _fail(
                "合成规则集的 basis.doc_code 必须以 %r 开头，实际 %r"
                % (SYNTHETIC_MARKER, basis.get("doc_code"))
            )
        if not str(basis.get("doc_title") or "").startswith(SYNTHETIC_MARKER):
            _fail("合成规则集的 basis.doc_title 必须以 %r 开头" % SYNTHETIC_MARKER)
        if str(basis.get("issuer") or "").strip():
            _fail("合成规则集不得填写真实发布机关（issuer 必须为空）")

    factors = obj.get("factors")
    if not isinstance(factors, list):
        _fail("factors 必须是数组")
    optional_policy = obj.get("optional_items_policy", "any")
    if optional_policy not in OPTIONAL_ITEMS_POLICIES:
        _fail(
            "optional_items_policy %r 非法（合法值：%s）"
            % (optional_policy, ", ".join(OPTIONAL_ITEMS_POLICIES))
        )
    seen_ids = set()
    seen_codes = set()
    for idx, factor in enumerate(factors):
        _validate_factor(factor, idx, optional_policy, synthetic)
        fid = factor["factor_id"]
        code = factor["factor_code"]
        if fid in seen_ids:
            _fail("factor_id 重复：%s" % fid)
        if code in seen_codes:
            _fail("factor_code 重复：%s" % code)
        seen_ids.add(fid)
        seen_codes.add(code)
    return obj


def validate_manifest(obj):
    """校验 manifest（含 cutover 与 benchmark_thresholds）。"""
    if not isinstance(obj, dict):
        _fail("manifest 根必须是对象")
    if obj.get("schema_version") != SCHEMA_VERSION:
        _fail("manifest.schema_version 必须是 %r" % SCHEMA_VERSION)

    cutover = obj.get("cutover")
    if not isinstance(cutover, dict):
        _fail("manifest 缺少 cutover 对象")
    for key in ("date", "before", "after"):
        if not str(cutover.get(key) or "").strip():
            _fail("manifest.cutover 缺少非空字段 %r" % key)

    if not isinstance(obj.get("rulesets"), list):
        _fail("manifest.rulesets 必须是数组")

    thresholds = obj.get("benchmark_thresholds")
    if not isinstance(thresholds, dict):
        _fail(
            "manifest 缺少 benchmark_thresholds——门槛随 manifest 下发（数据非代码），"
            "不得回落代码默认值"
        )
    return obj
