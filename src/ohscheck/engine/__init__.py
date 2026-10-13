"""判定层：确定性内核（纯函数，无 IO、不计时）。

分层铁律（决策 D-31）：`(输入, EffectiveRuleset) → 结果对象`。
IO 只在编排层（pipeline）与基础层（paths/loaders）。
"""

from __future__ import annotations

from .coverage import check_record
from .matrix import compute_plan, plan_for_factor
from .period import add_months, judge_period
from .scan import scan_directory

__all__ = [
    "check_record",
    "compute_plan",
    "plan_for_factor",
    "add_months",
    "judge_period",
    "scan_directory",
]
