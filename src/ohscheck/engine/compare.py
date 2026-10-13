"""版本差异对照（FR-C3）。

门控范围（plan/03 §五）：scope="compare" 只校验结构字段，
**不要求项目明细 verified**——否则"项目待核对"会阻断版本对照本身。
"""

from __future__ import annotations

from ..model import EXAM_TYPES


class DiffEntry:
    """一条差异。"""

    __slots__ = ("kind", "key", "label", "detail", "basis_a", "basis_b")

    def __init__(self, kind, key, label, detail="", basis_a="", basis_b=""):
        self.kind = kind
        self.key = key
        self.label = label
        self.detail = detail
        self.basis_a = basis_a
        self.basis_b = basis_b

    def as_dict(self):
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "detail": self.detail,
            "basis_a": self.basis_a,
            "basis_b": self.basis_b,
        }


class DiffReport:
    """差异报告。"""

    __slots__ = ("ruleset_a", "ruleset_b", "entries", "notes")

    def __init__(self, ruleset_a, ruleset_b, entries=None, notes=None):
        self.ruleset_a = ruleset_a
        self.ruleset_b = ruleset_b
        self.entries = list(entries or [])
        self.notes = list(notes or [])

    def by_kind(self, kind):
        return [e for e in self.entries if e.kind == kind]

    def as_dict(self):
        return {
            "ruleset_a": self.ruleset_a,
            "ruleset_b": self.ruleset_b,
            "entries": [e.as_dict() for e in self.entries],
            "notes": list(self.notes),
        }


def _factor_codes(eff):
    return set(eff.ruleset.factor_codes)


def _basis_of(eff, code):
    factor = eff.ruleset.factor(code)
    if factor is None:
        return ""
    return "%s 第 %s 节" % (
        (factor.get("basis") or {}).get("doc_code") or eff.ruleset.basis.get("doc_code", ""),
        factor.get("factor_id", ""),
    )


def compare_rulesets(eff_a, eff_b):
    """对照两份规则集（A=旧，B=新）。

    对照维度（plan/04 §七）：
        1. 危害因素覆盖（新增 / 删除）
        2. 检查时点存在性
        3. 必检项目构成（code 集合）
        4. 选检项目调整（非空 → 空）
    """
    codes_a = _factor_codes(eff_a)
    codes_b = _factor_codes(eff_b)
    entries = []

    for code in sorted(codes_b - codes_a):
        entries.append(
            DiffEntry(
                "factor_added",
                code,
                "新增危害因素：%s" % eff_b.ruleset.factor(code)["factor_name"],
                basis_b=_basis_of(eff_b, code),
            )
        )
    for code in sorted(codes_a - codes_b):
        entries.append(
            DiffEntry(
                "factor_removed",
                code,
                "删除危害因素：%s" % eff_a.ruleset.factor(code)["factor_name"],
                basis_a=_basis_of(eff_a, code),
            )
        )

    for code in sorted(codes_a & codes_b):
        fa = eff_a.ruleset.factor(code)
        fb = eff_b.ruleset.factor(code)
        for exam_type in EXAM_TYPES:
            block_a = fa["examinations"][exam_type]
            block_b = fb["examinations"][exam_type]
            req_a = {i.get("item_code") for i in block_a.get("required_items") or []}
            req_b = {i.get("item_code") for i in block_b.get("required_items") or []}
            if req_a != req_b:
                added = sorted(req_b - req_a)
                removed = sorted(req_a - req_b)
                detail = []
                if added:
                    detail.append("新增 %s" % ", ".join(added))
                if removed:
                    detail.append("删除 %s" % ", ".join(removed))
                entries.append(
                    DiffEntry(
                        "required_items_changed",
                        "%s/%s" % (code, exam_type),
                        "%s 的 %s 必检项目构成变化" % (fa["factor_name"], exam_type),
                        detail="；".join(detail),
                        basis_a=_basis_of(eff_a, code),
                        basis_b=_basis_of(eff_b, code),
                    )
                )
            opt_a = block_a.get("optional_items") or []
            opt_b = block_b.get("optional_items") or []
            if (not opt_a) != (not opt_b):
                entries.append(
                    DiffEntry(
                        "optional_items_adjusted",
                        "%s/%s" % (code, exam_type),
                        "%s 的 %s 选检项目调整" % (fa["factor_name"], exam_type),
                        detail="由 %d 项变为 %d 项" % (len(opt_a), len(opt_b)),
                        basis_a=_basis_of(eff_a, code),
                        basis_b=_basis_of(eff_b, code),
                    )
                )
        if fa["period"].get("kind") != fb["period"].get("kind") or fa["period"].get(
            "value"
        ) != fb["period"].get("value"):
            entries.append(
                DiffEntry(
                    "period_changed",
                    code,
                    "%s 检查周期变化" % fa["factor_name"],
                    detail="%s/%s → %s/%s"
                    % (
                        fa["period"].get("kind"),
                        fa["period"].get("value"),
                        fb["period"].get("kind"),
                        fb["period"].get("value"),
                    ),
                    basis_a=_basis_of(eff_a, code),
                    basis_b=_basis_of(eff_b, code),
                )
            )

    notes = []
    if not entries:
        notes.append(
            "两版结构对照无差异条目。注意：若某规则集条目为 pending，"
            "本差异仅为结构对照，条目级差异待规则入库后生效。"
        )
    return DiffReport(eff_a.ruleset_id, eff_b.ruleset_id, entries, notes)
