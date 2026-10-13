"""报告章节结构——**单一渲染源**（决策 D-33）。

Markdown 与 XLSX 都消费本模块的 report_sections()，
于是"两格式内容一致"成为结构性质而非人工抽查。

章节清单见 plan/04 §8.2。"未启用"的章节必须**显式写出**（决策 D-35）：
"没查"与"查了没问题"是两种截然不同的结论，留空会被误读成后者。
"""

from __future__ import annotations

from ..model import EXAM_TYPE_LABELS, VERDICT_LABELS


class Table:
    """一张表（headers + rows）。"""

    __slots__ = ("title", "headers", "rows")

    def __init__(self, title, headers, rows):
        self.title = title
        self.headers = list(headers)
        self.rows = [list(r) for r in rows]

    def as_dict(self):
        return {"title": self.title, "headers": list(self.headers),
                "rows": [list(r) for r in self.rows]}


class Section:
    """一个章节。"""

    __slots__ = ("number", "title", "paragraphs", "tables", "notes")

    def __init__(self, number, title, paragraphs=None, tables=None, notes=None):
        self.number = number
        self.title = title
        self.paragraphs = list(paragraphs or [])
        self.tables = list(tables or [])
        self.notes = list(notes or [])

    def as_dict(self):
        return {
            "number": self.number,
            "title": self.title,
            "paragraphs": list(self.paragraphs),
            "tables": [t.as_dict() for t in self.tables],
            "notes": list(self.notes),
        }


DISCLAIMER = (
    "本报告为**基于标准的监护合规检查发现**，不构成医学意见、职业病诊断或行政认定；"
    "正式结论以职业健康检查机构与卫生健康行政部门口径为准。"
    "规则条目核对状态以规则包 status 为准，pending 条目不参与任何核查或判定。"
)


class ReportModel:
    """报告模型（供章节函数消费）。"""

    __slots__ = (
        "ruleset_id",
        "generated_at",
        "parameter_sources",
        "plan_result",
        "coverage_results",
        "scan_result",
        "reconcile_result",
        "gate_rows",
    )

    def __init__(self, ruleset_id="", generated_at=None, parameter_sources=None,
                 plan_result=None, coverage_results=None, scan_result=None,
                 reconcile_result=None, gate_rows=None):
        self.ruleset_id = ruleset_id
        self.generated_at = generated_at
        self.parameter_sources = list(parameter_sources or [])
        self.plan_result = plan_result
        self.coverage_results = list(coverage_results or [])
        self.scan_result = scan_result
        self.reconcile_result = reconcile_result
        self.gate_rows = list(gate_rows or [])


def build_model(*, plan_result=None, coverage_results=None, scan_result=None,
                reconcile_result=None, context=None, ruleset_id=None, generated_at=None):
    """从编排层产物构造报告模型。"""
    from ..engine.pipeline import gate_overview, parameter_overview

    sources = parameter_overview(context) if context is not None else []
    gate_rows = gate_overview(context) if context is not None else []
    if ruleset_id is None:
        if plan_result is not None:
            ruleset_id = plan_result.ruleset_id
        elif scan_result is not None and scan_result.items:
            ruleset_id = ""
    return ReportModel(
        ruleset_id=ruleset_id or "",
        generated_at=generated_at,
        parameter_sources=sources,
        plan_result=plan_result,
        coverage_results=coverage_results,
        scan_result=scan_result,
        reconcile_result=reconcile_result,
        gate_rows=gate_rows,
    )


def _header_section(model):
    paragraphs = [
        "规则包坐标：依据版本 **%s**；版本号 schema 1.0；生成时间 %s"
        % (model.ruleset_id or "（未指定）", model.generated_at or "（未注入）"),
        DISCLAIMER,
    ]
    return Section("0", "报告头与规则包坐标", paragraphs=paragraphs)


def _input_section(model):
    paragraphs = []
    if model.plan_result is not None:
        paragraphs.append(
            "岗位画像：%s；体检日期锚定版本 %s"
            % (model.plan_result.position_id, model.plan_result.ruleset_id)
        )
    if model.coverage_results:
        paragraphs.append("核查档案 %d 份" % len(model.coverage_results))
    if model.scan_result is not None:
        paragraphs.append(
            "批量扫描：判定 %d 份，未判定 %d 份"
            % (len(model.scan_result.items), len(model.scan_result.failed))
        )
    if not paragraphs:
        paragraphs.append("本次导出未含输入事实（未提供岗位画像或档案）。")
    return Section("1", "输入事实", paragraphs=paragraphs)


def _factor_section(model):
    if model.plan_result is None:
        return Section(
            "2",
            "岗位危害因素画像",
            paragraphs=["本次导出未启用岗位画像（用 plan 子命令生成应检清单）。"],
        )
    rows = []
    for factor_plan in model.plan_result.factors:
        app = factor_plan.applicability
        rows.append(
            [
                factor_plan.factor_code,
                factor_plan.factor_name,
                app.state,
                app.reason,
                factor_plan.basis,
            ]
        )
    return Section(
        "2",
        "岗位危害因素画像",
        tables=[Table("危害因素与适用性", ["因素代码", "名称", "适用性", "判据", "条款依据"], rows)],
    )


def _plan_section(model):
    if model.plan_result is None:
        return Section(
            "3",
            "应检清单与条款依据",
            paragraphs=["本次导出未启用应检清单（用 plan 子命令生成）。"],
        )
    rows = []
    for factor_plan in model.plan_result.factors:
        if factor_plan.applicability.state != "applicable":
            rows.append(
                [
                    factor_plan.factor_code,
                    "—",
                    "—",
                    "（%s：%s）" % (factor_plan.applicability.state, factor_plan.applicability.reason),
                    factor_plan.basis,
                ]
            )
            continue
        for exam_type, exam in sorted(factor_plan.exams.items()):
            rows.append(
                [
                    factor_plan.factor_code,
                    EXAM_TYPE_LABELS.get(exam_type, exam_type),
                    "、".join(exam.required_items) or "（无必检项）",
                    "补充 %d 项 / 选检 %d 项" % (len(exam.supplementary_items), len(exam.optional_items)),
                    exam.basis,
                ]
            )
    trace_rows = [
        [t.get("target", ""), t.get("value", ""), t.get("basis", "")]
        for t in model.plan_result.trace
    ]
    return Section(
        "3",
        "应检清单与条款依据",
        tables=[
            Table(
                "四时点应检项目（判定用 = 必检项；补充/选检项不进判定）",
                ["因素代码", "检查时点", "必检项目", "其他", "条款依据"],
                rows,
            ),
            Table("溯源明细（每行挂条款依据）", ["目标", "取值", "条款依据"], trace_rows),
        ],
        notes=[
            "应检项集只取必检项（决策 D-16）；补充项目与选检项目的缺失不判为缺项。",
            "工具不做「该做补充检查没做」的判定——补充项目的条件由临床判断，不在确定性规则能力内。",
        ],
    )


def _coverage_section(model):
    if not model.coverage_results:
        return Section(
            "4",
            "覆盖核查明细",
            paragraphs=["本次导出未启用覆盖核查（用 check/scan 子命令生成）。"],
        )
    rows = []
    for rec in model.coverage_results:
        rows.append(
            [
                rec.record_id,
                rec.employee_id,
                rec.factor_code,
                EXAM_TYPE_LABELS.get(rec.exam_type, rec.exam_type),
                VERDICT_LABELS.get(rec.verdict, rec.verdict),
                "、".join(rec.missing_items) or "—",
                "、".join(rec.unmapped_items) or "—",
            ]
        )
    finding_rows = []
    for rec in model.coverage_results:
        for finding in rec.findings:
            finding_rows.append(
                [
                    rec.record_id,
                    finding.get("kind", ""),
                    finding.get("item_code", "") or "—",
                    finding.get("message", ""),
                    finding.get("basis", ""),
                ]
            )
    return Section(
        "4",
        "覆盖核查明细",
        tables=[
            Table(
                "逐人四态判定",
                ["档案", "人员", "因素", "时点", "结论", "缺项", "未归一实检项"],
                rows,
            ),
            Table("发现明细（缺项 / 降级警告 / 周期）", ["档案", "类型", "项目", "说明", "条款依据"], finding_rows),
        ],
        notes=["别名归一不成立的实检项降级为 warning，不判为缺失（决策 D-17）。"],
    )


def _period_section(model):
    target = model.coverage_results or []
    if not target and model.scan_result is None:
        return Section(
            "5",
            "周期合规",
            paragraphs=["本次导出未启用周期合规判定。"],
        )
    rows = []
    for rec in target:
        rows.append(
            [
                rec.record_id,
                EXAM_TYPE_LABELS.get(rec.exam_type, rec.exam_type),
                rec.period_verdict or "—",
            ]
        )
    return Section(
        "5",
        "周期合规",
        tables=[Table("周期判定", ["档案", "时点", "周期结论"], rows)] if rows else None,
        paragraphs=[] if rows else ["本次导出未含在岗期间档案，无周期判定结果。"],
        notes=[
            "周期判定基于本次体检日期与上次检查日期，不使用「今天」，保证可复现（决策 D-18）。",
            "到期当日检查计入合规；无基线的首次检查不报超期。",
        ],
    )


def _stats_section(model):
    if model.scan_result is None:
        return Section(
            "6",
            "群体统计",
            paragraphs=["本次导出未启用群体统计（用 scan 子命令生成）。"],
        )
    stats = model.scan_result.stats or model.scan_result.compute_stats()
    rows = []
    for bucket in stats.get("by_factor", []):
        rows.append(
            [
                bucket["factor_code"],
                bucket["examined"],
                bucket["compliant"],
                bucket["noncompliant"],
                bucket["not_applicable"],
                bucket["unknown"],
            ]
        )
    return Section(
        "6",
        "群体统计",
        tables=[
            Table(
                "按危害因素汇总",
                ["因素代码", "已判定", "符合", "不符合/部分", "不适用", "待确认"],
                rows,
            )
        ],
        notes=["未判定 %d 份单列于失败件清单，不计入上述统计。" % stats.get("failed", 0)],
    )


def _reconcile_section(model):
    if model.reconcile_result is None:
        return Section(
            "7",
            "跨轮对账",
            paragraphs=["本次导出未启用跨轮对账（用 --baseline 启用）。"],
        )
    rec = model.reconcile_result
    return Section(
        "7",
        "跨轮对账",
        tables=[
            Table(
                "三主集 + 两辅助集",
                ["集合", "条数", "明细"],
                [
                    ["新增缺项", len(rec.new_missing), _fmt_items(rec.new_missing)],
                    ["已补齐", len(rec.resolved), _fmt_items(rec.resolved)],
                    ["持续缺失", len(rec.persistent), _fmt_items(rec.persistent)],
                    ["新增档案", len(rec.aux.get("new_records", [])), "、".join(rec.aux.get("new_records", []))],
                    ["消失档案", len(rec.aux.get("gone_records", [])), "、".join(rec.aux.get("gone_records", []))],
                ],
            )
        ],
        notes=["配对主键为人员稳定 ID + 缺项坐标，非内容指纹（决策 D-20）。"],
    )


def _fmt_items(items):
    parts = []
    for item in items[:20]:
        parts.append("%s@%s" % (item.get("employee_id", ""), item.get("target", "")))
    if len(items) > 20:
        parts.append("…等 %d 项" % len(items))
    return "；".join(parts) or "—"


def _rectify_section(model):
    rows = []
    for rec in model.coverage_results:
        for finding in rec.findings:
            if finding.get("kind") == "missing_item":
                rows.append(
                    [
                        rec.employee_id,
                        rec.factor_code,
                        finding.get("item_code", ""),
                        "建议安排补检",
                        finding.get("basis", ""),
                    ]
                )
            elif finding.get("kind") == "period_overdue":
                rows.append(
                    [rec.employee_id, rec.factor_code, "—", "建议按周期安排复查", finding.get("basis", "")]
                )
    if not rows:
        return Section(
            "8",
            "整改台账",
            paragraphs=["本次未检出需整改的缺项或超期项。"],
        )
    return Section(
        "8",
        "整改台账",
        tables=[Table("整改建议", ["人员", "因素", "缺项", "建议", "条款依据"], rows)],
        notes=["以上为基于标准条文的检查建议，不构成行政指令。"],
    )


def _parameter_section(model):
    if not model.parameter_sources:
        return Section(
            "9",
            "参数来源块",
            paragraphs=["本次导出未附带规则包参数来源（未提供规则包上下文）。"],
        )
    rows = []
    for src in model.parameter_sources:
        rows.append(
            [
                src.get("ruleset_id", ""),
                src.get("doc_code", ""),
                src.get("issuer", ""),
                src.get("doc_number", ""),
                src.get("published", ""),
                src.get("effective_from", ""),
                src.get("fetched", ""),
                src.get("sha256", ""),
            ]
        )
    urls = []
    for src in model.parameter_sources:
        if src.get("url"):
            urls.append("%s → %s" % (src.get("ruleset_id", ""), src["url"]))
    if urls:
        rows.append(["来源 URL（纯文本）", "", "", "", "", "", "", ""])
        for line in urls:
            rows.append([line, "", "", "", "", "", "", ""])
    return Section(
        "9",
        "参数来源块",
        tables=[
            Table(
                "规则包出处（发布机关 / 文号 / 生效 / 抓取 / 指纹）",
                ["规则集", "标准号", "发布机关", "文号", "发布日期", "生效日期", "抓取日期", "sha256"],
                rows,
            )
        ],
        notes=["URL 以纯文本列示，产物无外链，断网可开（决策 D-34）。"],
    )


def _failed_section(model):
    if model.scan_result is None:
        return Section(
            "10",
            "失败件清单",
            paragraphs=["本次导出未启用批量扫描，无失败件统计。"],
        )
    if not model.scan_result.failed:
        return Section("10", "失败件清单", paragraphs=["本次无失败件。"])
    rows = [[f.path, f.reason, f.message] for f in model.scan_result.failed]
    return Section(
        "10",
        "失败件清单",
        tables=[Table("未判定档案（原因码单列）", ["文件", "原因码", "说明"], rows)],
        notes=[
            "失败件为**未判定**，不等于违规，不改变退出码（决策 D-21）。",
        ],
    )


def _disclaimer_section(model):
    return Section("11", "免责声明", paragraphs=[DISCLAIMER])


def report_sections(model):
    """★唯一章节结构函数：Markdown 与 XLSX 都消费它。"""
    return [
        _header_section(model),
        _input_section(model),
        _factor_section(model),
        _plan_section(model),
        _coverage_section(model),
        _period_section(model),
        _stats_section(model),
        _reconcile_section(model),
        _rectify_section(model),
        _parameter_section(model),
        _failed_section(model),
        _disclaimer_section(model),
    ]
