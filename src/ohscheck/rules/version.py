# 版本锚定：按体检日期选规则版本（决策 D-10 / D-11，口径 T3–T5）。
#
# 锚定键 = **体检日期 exam_date**（不是编制年度、不是"年度"）：
#     档案的合规义务按其**检查发生日**适用当时有效的标准。
#
# 切口日两侧：切口日之前 → cutover.before；切口日当日及之后 → cutover.after。
#
# 只给年度且该年度包含切口日 → AmbiguousYearError（**宁报错不猜**）：
# 切口日所在自然年内两版并存（切口日之前适用旧版、当日及之后适用新版），
# 用年度锚定必然把一半档案算错版本。
# 注：切口日与版本号一律读自 manifest（数据），代码里不出现年份字面量。

from __future__ import annotations

import datetime as _dt

from ..errors import AmbiguousYearError, InputError
from ..model import parse_iso_date


def parse_cutover_date(manifest):
    """从 manifest 读切口日（代码零硬编码）。"""
    return parse_iso_date(manifest.cutover_date_text, "manifest.cutover.date")


def resolve_ruleset_id(exam_date, manifest):
    """按体检日期解析适用的 ruleset_id。

    Args:
        exam_date: datetime.date / ISO 字符串 / 年份 int。
        manifest: Manifest。

    Returns:
        ruleset_id 字符串。

    Raises:
        AmbiguousYearError: 只给年度且该年度含切口日。
        InputError: 参数类型非法或切口日配置缺失。
    """
    cutover = parse_cutover_date(manifest)

    if isinstance(exam_date, int) and not isinstance(exam_date, bool):
        if exam_date == cutover.year:
            raise AmbiguousYearError(exam_date, cutover.isoformat())
        return manifest.cutover["after"] if exam_date > cutover.year else manifest.cutover["before"]

    if isinstance(exam_date, str):
        text = exam_date.strip()
        # 只给了年度（四位数字）→ 走年度分支
        if len(text) == 4 and text.isdigit():
            return resolve_ruleset_id(int(text), manifest)
        exam_date = parse_iso_date(text)

    if not isinstance(exam_date, _dt.date):
        raise InputError("exam_date 必须是 ISO 日期字符串、date 或年份整数，实际 %r" % (exam_date,))

    return manifest.cutover["after"] if exam_date >= cutover else manifest.cutover["before"]


def describe_anchor(exam_date, manifest):
    """锚定结果的可读说明（报告头与 selfcheck 用）。"""
    cutover = parse_cutover_date(manifest)
    ruleset_id = resolve_ruleset_id(exam_date, manifest)
    return {
        "exam_date": exam_date if isinstance(exam_date, str) else str(exam_date),
        "cutover_date": cutover.isoformat(),
        "ruleset_id": ruleset_id,
        "rule": "exam_date >= cutover_date ? after : before",
    }
