"""Markdown 渲染器（人读）。

无外链（决策 D-34）：正文不出现 http(s) 链接语法；URL 只作纯文本落在 §9。
落盘用 write_bytes + 显式 LF；生成时间由调用方注入，不读系统时钟。
"""

from __future__ import annotations

from .sections import report_sections


def _cell(value):
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _render_table(table, out):
    if table.title:
        out.append("**%s**" % table.title)
        out.append("")
    if not table.headers:
        return
    out.append("| " + " | ".join(_cell(h) for h in table.headers) + " |")
    out.append("|" + "|".join([" --- "] * len(table.headers)) + "|")
    for row in table.rows:
        cells = [_cell(c) for c in row]
        while len(cells) < len(table.headers):
            cells.append("")
        out.append("| " + " | ".join(cells[: len(table.headers)]) + " |")
    out.append("")


def render_markdown(model, sections=None):
    """渲染为 Markdown 文本（LF 行尾）。"""
    sections = sections if sections is not None else report_sections(model)
    out = ["# 职业健康监护合规核查报告", ""]
    for section in sections:
        out.append("## %s %s" % (section.number, section.title))
        out.append("")
        for para in section.paragraphs:
            out.append(para)
            out.append("")
        for table in section.tables:
            _render_table(table, out)
        for note in section.notes:
            out.append("> %s" % note)
            out.append("")
    text = "\n".join(out)
    return text.rstrip("\n") + "\n"
