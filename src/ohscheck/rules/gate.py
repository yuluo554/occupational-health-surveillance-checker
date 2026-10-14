"""status 门控：按计算路径分作用域（决策 D-12 / D-13）。

核心纪律：门控问的是"**这次计算用到的条目**核对了吗"，不是"整包核对了吗"——
后者会让与本次计算无关的 pending 条目阻断法定路径。

作用域（plan/03 §五）：
    plan    矩阵推导/应检清单 —— 校验本次推导引用的 factor 条目全字段
    check   覆盖度 + 周期判定 —— 同上
    compare 版本差异对照       —— 只校验结构字段，不要求项目明细 verified
    bench   基准               —— 同 compare 的宽口径

第三态 input_required **放行门控**，但运行时必须显式索取（见 missing_inputs）。
"""

from __future__ import annotations

from ..errors import GateBlocked, InputError

SCOPES = ("plan", "check", "compare", "bench")

# 每作用域的核对深度
#   full    : 因素条目 + 适用性 + 周期 + 四时点全部项目
#   minimal : 仅结构字段（对照/基准用）
SCOPE_DEPTH = {
    "plan": "full",
    "check": "full",
    "compare": "minimal",
    "bench": "minimal",
}


class EffectiveRuleset:
    """门控通过后的规则集视图。

    Attributes:
        ruleset: 原始 Ruleset。
        scope: 作用域。
        used_factor_codes: 本次计算实际引用的因素代码（已排序）。
        missing_inputs: input_required 条目清单（[{target, basis, factor_code}]）。
    """

    __slots__ = ("ruleset", "scope", "used_factor_codes", "missing_inputs")

    def __init__(self, ruleset, scope, used_factor_codes, missing_inputs=None):
        self.ruleset = ruleset
        self.scope = scope
        self.used_factor_codes = sorted(used_factor_codes)
        self.missing_inputs = list(missing_inputs or [])

    @property
    def ruleset_id(self):
        return self.ruleset.ruleset_id

    def factor(self, code):
        return self.ruleset.factor(code)

    def has_factor(self, code):
        return self.ruleset.has_factor(code)


def _collect_full(factor):
    """full 深度：返回 (pending 坐标列表, input_required 清单)。

    **阻塞性分级**（M1 实测发现 A，见 plan/05 M1 发现表）：`input_required` 有两类，
    后果截然不同——
      * `blocking=True`（eligibility / 项目级）：不提供就无法确定**该不该做、做哪些**
        应检项 → 必须拦下（决策 D-13：绝不静默取默认值）；
      * `blocking=False`（period 级）：应检项**已可完全推导**，只是"周期"这一项
        标准按作业分级/接触水平分档、规则包不承载单值 → 应**降级为待输入**而非
        阻断整个核查。`judge_period` 早已按此返回 `input_required` 判定，
        若门控在此拦截，则 FR-B4 在**最需要判周期的那批因素上不可达**（假不可用）。
    """
    pending = []
    required_inputs = []
    code = factor["factor_code"]
    label = "%s(%s)" % (factor["factor_id"], code)

    for name, block in (
        ("", factor),
        ("eligibility", factor["eligibility"]),
        ("period", factor["period"]),
    ):
        status = block.get("status")
        where = "%s.%s" % (label, name) if name else label
        if status == "pending":
            pending.append(where)
        elif status == "input_required":
            required_inputs.append(
                {
                    "target": where,
                    "basis": block.get("basis", ""),
                    "factor_code": code,
                    # 周期级待输入不阻断：应检项已可推导（见上）
                    "blocking": name != "period",
                }
            )

    for di, disease in enumerate(factor.get("target_diseases") or []):
        if disease.get("status") == "pending":
            pending.append("%s.target_diseases[%d]" % (label, di))

    for key in ("pre_placement", "periodic", "post_placement", "emergency"):
        block = factor["examinations"][key]
        if block.get("status") == "pending":
            pending.append("%s.examinations.%s" % (label, key))
        for group in ("required_items", "supplementary_items", "optional_items"):
            for ii, item in enumerate(block.get(group) or []):
                item_where = "%s.examinations.%s.%s[%d]" % (label, key, group, ii)
                if item.get("status") == "pending":
                    pending.append(item_where)
                elif item.get("status") == "input_required":
                    required_inputs.append(
                        {
                            "target": item_where,
                            "basis": item.get("basis", ""),
                            "factor_code": code,
                            "blocking": True,
                        }
                    )
    return pending, required_inputs


def _collect_minimal(factor):
    """minimal 深度：只拦"整条因素标 pending"；不要求项目明细已核对。

    结构字段（factor_id/code/name/chapter/category 与四时点键集）由 schema 校验保证，
    本深度不重复拦截——否则"项目明细待核对"会阻断版本对照与基准。
    """
    pending = []
    required_inputs = []
    code = factor["factor_code"]
    if factor.get("status") == "pending":
        pending.append("%s(%s)" % (factor["factor_id"], code))
    if factor["eligibility"].get("status") == "input_required":
        required_inputs.append(
            {
                "target": "%s(%s).eligibility" % (factor["factor_id"], code),
                "basis": factor["eligibility"].get("basis", ""),
                "factor_code": code,
                "blocking": True,
            }
        )
    return pending, required_inputs


def _resolve_codes(ruleset, required_factor_ids):
    if required_factor_ids is None:
        return ruleset.factor_codes
    codes = sorted(set(required_factor_ids))
    unknown = [c for c in codes if not ruleset.has_factor(c)]
    if unknown:
        raise InputError(
            "规则集 %s 中不存在危害因素：%s" % (ruleset.ruleset_id, ", ".join(unknown)),
            reason="unknown_factor",
        )
    return codes


def effective_ruleset(ruleset, scope, required_factor_ids=None):
    """按作用域放行规则包；引用到的未核对条目一律拦截。

    Args:
        ruleset: Ruleset（已 schema 校验）。
        scope: plan / check / compare / bench。
        required_factor_ids: 本次计算引用到的因素代码；None = 整包（仅 compare/bench 适合）。

    Returns:
        EffectiveRuleset（含 missing_inputs）。

    Raises:
        ValueError: scope 非法。
        InputError: 引用了规则集中不存在的因素。
        GateBlocked: 引用到的条目里有 pending。
    """
    if scope not in SCOPES:
        raise ValueError("未知门控作用域 %r（合法值：%s）" % (scope, ", ".join(SCOPES)))
    collector = _collect_full if SCOPE_DEPTH[scope] == "full" else _collect_minimal

    codes = _resolve_codes(ruleset, required_factor_ids)
    pending = []
    missing_inputs = []
    for code in codes:
        p, m = collector(ruleset.factor(code))
        pending.extend(p)
        missing_inputs.extend(m)

    if pending:
        raise GateBlocked(scope, pending)

    return EffectiveRuleset(ruleset, scope, codes, missing_inputs)


def pending_report(ruleset, scope="plan", required_factor_ids=None):
    """不抛错的门控查询：返回 (pending 坐标, input_required 清单)。

    selfcheck 与报告用——如实呈现"哪些条目尚未核对"。
    """
    collector = _collect_full if SCOPE_DEPTH.get(scope, "minimal") == "full" else _collect_minimal
    try:
        codes = _resolve_codes(ruleset, required_factor_ids)
    except InputError:
        return ([], [])
    pending = []
    missing_inputs = []
    for code in codes:
        p, m = collector(ruleset.factor(code))
        pending.extend(p)
        missing_inputs.extend(m)
    return pending, missing_inputs
