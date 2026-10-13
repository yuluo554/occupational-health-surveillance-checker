"""规则层：加载、schema 校验、status 门控、版本锚定。

分层：本包只做"规则数据 → EffectiveRuleset"的转换，不含任何判定。
"""

from __future__ import annotations

from .gate import effective_ruleset
from .loader import load_manifest, load_ruleset
from .schema import validate_manifest, validate_ruleset
from .version import resolve_ruleset_id

__all__ = [
    "effective_ruleset",
    "load_manifest",
    "load_ruleset",
    "validate_manifest",
    "validate_ruleset",
    "resolve_ruleset_id",
]
