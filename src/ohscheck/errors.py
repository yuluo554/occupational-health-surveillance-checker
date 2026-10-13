"""原因码与异常。

退出码契约见 plan/03-架构与技术选型.md §七：
    0 成功且无不符合项 / 基准全达标
    1 成功但检出不符合 / 基准未达标
    2 用法、输入或坐标错误（含门控拦截与 input_required 未提供）
    3 可选依赖缺失

判定层不直接 sys.exit；判定层抛本模块的异常，由 CLI 统一映射为退出码。
"""

from __future__ import annotations

# ---- 退出码 ----
EXIT_OK = 0
EXIT_NONCOMPLIANT = 1
EXIT_USAGE = 2
EXIT_MISSING_DEPENDENCY = 3

# ---- 原因码（失败件单列，不改变退出码：见决策 D-21）----
REASON_READ_ERROR = "read_error"
REASON_BAD_JSON = "bad_json"
REASON_SCHEMA_INVALID = "schema_invalid"
REASON_UNKNOWN_FACTOR = "unknown_factor"
REASON_UNKNOWN_EXAM_TYPE = "unknown_exam_type"
REASON_CONTAINER_TOO_LARGE = "container_too_large"
REASON_GATE_BLOCKED = "gate_blocked"
REASON_MISSING_INPUT = "missing_input"
REASON_UNMAPPED_ITEM = "unmapped_item"

# 批量扫描中"未判定"的原因码集合——这些不改变退出码
UNJUDGED_REASONS = frozenset(
    {
        REASON_READ_ERROR,
        REASON_BAD_JSON,
        REASON_SCHEMA_INVALID,
        REASON_UNKNOWN_FACTOR,
        REASON_UNKNOWN_EXAM_TYPE,
        REASON_CONTAINER_TOO_LARGE,
        REASON_GATE_BLOCKED,
        REASON_MISSING_INPUT,
    }
)


class OhsCheckError(Exception):
    """本工具所有可预期错误的基类。

    Attributes:
        reason: 原因码（见上方 REASON_*）。
        exit_code: CLI 应返回的退出码。
    """

    reason = "error"
    exit_code = EXIT_USAGE

    def __init__(self, message, reason=None, exit_code=None):
        super().__init__(message)
        self.message = message
        if reason is not None:
            self.reason = reason
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(OhsCheckError):
    """参数/用法错误。"""

    reason = "usage_error"
    exit_code = EXIT_USAGE


class InputError(OhsCheckError):
    """输入不可用（文件不存在、坏 JSON、schema 不合法）。"""

    reason = REASON_SCHEMA_INVALID
    exit_code = EXIT_USAGE


class GateBlocked(OhsCheckError):
    """status 门控拦截：本次计算引用到的规则条目尚未核对。

    pending 条目绝不参与任何核查或判定（决策 D-12 / D-13）。
    """

    reason = REASON_GATE_BLOCKED
    exit_code = EXIT_USAGE

    def __init__(self, scope, blocked):
        self.scope = scope
        self.blocked = list(blocked)
        coords = ", ".join(self.blocked[:8])
        more = "" if len(self.blocked) <= 8 else "（等 %d 项）" % len(self.blocked)
        super().__init__(
            "规则包门控拦截：scope=%s 引用了 %d 个未核对条目：%s%s。"
            "未挂原文核对的条目不得进入核查路径。" % (scope, len(self.blocked), coords, more)
        )


class MissingInputError(OhsCheckError):
    """input_required：本不由规则包承载的外部输入未提供。"""

    reason = REASON_MISSING_INPUT
    exit_code = EXIT_USAGE

    def __init__(self, items):
        self.items = list(items)
        detail = "; ".join("%s：%s" % (it["target"], it["basis"]) for it in self.items[:8])
        super().__init__(
            "缺少 %d 项规则包不承载的外部输入，无法完成判定（绝不静默取默认值）：%s"
            % (len(self.items), detail)
        )


class AmbiguousYearError(OhsCheckError):
    """只给年度且该年度包含标准切口日 → 版本不可锚定。"""

    reason = "ambiguous_year"
    exit_code = EXIT_USAGE

    def __init__(self, year, cutover_date):
        super().__init__(
            "年度 %d 内含标准切口日 %s，同一批档案分属两版规则，无法用年度锚定版本。"
            "请给出精确体检日期（exam_date）。" % (year, cutover_date)
        )


class MissingThresholdError(OhsCheckError):
    """基准验收门槛缺失 → 配置错误（决策 D-24：不得回落代码默认值）。"""

    reason = "missing_threshold"
    exit_code = EXIT_USAGE

    def __init__(self, key):
        super().__init__(
            "规则包 manifest 缺少基准验收门槛 %r——门槛是数据不是代码，"
            "不得回落到内置默认值。请重新生成规则包。" % key
        )


class MissingDependencyError(OhsCheckError):
    """可选依赖缺失（如 GUI extra 未安装）。"""

    reason = "missing_dependency"
    exit_code = EXIT_MISSING_DEPENDENCY
