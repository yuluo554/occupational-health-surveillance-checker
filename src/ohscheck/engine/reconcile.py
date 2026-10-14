"""跨轮对账（FR-D3）。

三条硬纪律（决策 D-20）：
  ① **配对主键 = 稳定身份键**（employee_id + 缺项坐标），**不是内容指纹**。
     用内容指纹配对时"已补齐"必然内容变了 → 永远配不上 → **resolved 永远检不出**。
  ② 内容变化**另立** content_changed 标记，不让它退化成"新增 + 移除"。
  ③ 对账口径**单一实现源**（本模块函数供测试与基准共用）。

四类集（题目 §二.4 写的是"新增缺项 / 已补齐 / 持续缺失"，本模块为三主集 + 两辅助集）：
    new_missing  本轮缺、上轮不缺
    resolved     上轮缺、本轮不缺
    persistent   两轮都缺
    aux.new_records / aux.gone_records  按 employee_id 的件级增删
"""

from __future__ import annotations


class ReconcileResult:
    """跨轮对账结果。"""

    __slots__ = ("new_missing", "resolved", "persistent", "content_changed", "aux")

    def __init__(self, new_missing=None, resolved=None, persistent=None,
                 content_changed=None, aux=None):
        self.new_missing = list(new_missing or [])
        self.resolved = list(resolved or [])
        self.persistent = list(persistent or [])
        self.content_changed = list(content_changed or [])
        self.aux = aux or {}

    def as_dict(self):
        return {
            "new_missing": list(self.new_missing),
            "resolved": list(self.resolved),
            "persistent": list(self.persistent),
            "content_changed": list(self.content_changed),
            "aux": dict(self.aux),
        }


def missing_keys(coverage_result):
    """把一份核查结果摊成缺项键集合。

    键 = (employee_id, factor_code/exam_type/item_code)
    """
    out = set()
    for item_code in coverage_result.missing_items:
        out.add(
            (
                coverage_result.employee_id,
                "%s/%s/%s" % (coverage_result.factor_code, coverage_result.exam_type, item_code),
            )
        )
    return out


def record_keys(scan_result):
    """件级键集合（用于新增件/消失件）。"""
    return {r.employee_id for r in scan_result.items if r.employee_id}


def _record_states(scan_result):
    """人员 → 该人各缺项键的集合（配对主键 = employee_id + 缺项坐标，决策 D-20）。

    Returns:
        {employee_id: {(factor_code/exam_type/item_code), ...}}
    """
    states = {}
    for item in scan_result.items:
        if not item.employee_id:
            continue
        states.setdefault(item.employee_id, set()).update(missing_keys(item))
    return states


def compare_rounds(current_scan, baseline_scan):
    """本轮 vs 上轮对账。

    配对主键 = `employee_id` + 缺项坐标（稳定身份键，决策 D-20）：
      * 同一人员同一坐标两轮都缺   → persistent；
      * 上轮缺、本轮不缺           → resolved（"已补齐必须检得出"——内容变了
        恰恰是补齐的观测形态，所以主键必须是身份键而非内容指纹）；
      * 本轮缺、上轮不缺           → new_missing；
      * 同一人员缺项**集合变化**但缺项键既有增又有减时，减的进 resolved、
        增的进 new_missing；此外该人员进 `content_changed`（内容变化另立标记，
        不让它退化成"新增 + 移除"，决策 D-20 纪律②）。
    """
    cur_missing = set()
    base_missing = set()
    for item in current_scan.items:
        cur_missing |= missing_keys(item)
    for item in baseline_scan.items:
        base_missing |= missing_keys(item)

    new_missing = sorted(cur_missing - base_missing)
    resolved = sorted(base_missing - cur_missing)
    persistent = sorted(cur_missing & base_missing)

    # content_changed：同一人员两轮都有记录、但缺项键集合发生了变化
    cur_states = _record_states(current_scan)
    base_states = _record_states(baseline_scan)
    changed = []
    for employee_id in sorted(set(cur_states) & set(base_states)):
        if cur_states[employee_id] != base_states[employee_id]:
            changed.append({"employee_id": employee_id})

    cur_records = record_keys(current_scan)
    base_records = record_keys(baseline_scan)

    return ReconcileResult(
        new_missing=[_fmt(k) for k in new_missing],
        resolved=[_fmt(k) for k in resolved],
        persistent=[_fmt(k) for k in persistent],
        content_changed=changed,
        aux={
            "new_records": sorted(cur_records - base_records),
            "gone_records": sorted(base_records - cur_records),
        },
    )


def _fmt(key):
    employee_id, target = key
    return {"employee_id": employee_id, "target": target}


def has_new_missing(reconcile_result):
    """本轮是否出现新增缺项（整改退化信号）。"""
    return len(reconcile_result.new_missing) > 0
