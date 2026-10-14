"""页签 1：自检（数据定位 + 规则库 + 门控计数 + 参数来源）。"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..service import GUIError, Service
from . import widgets


def build(service):
    """自检页：一键 selfcheck，结果分块渲染。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    status_label = QLabel("尚未执行自检。")
    layout.addWidget(status_label)
    button = QPushButton("执行自检")
    layout.addWidget(button)

    detail = widgets.result_text("")
    detail.hide()
    layout.addWidget(detail)
    tables = []
    refresh = {"clear": lambda: _clear(tables, layout)}

    def on_click():
        refresh["clear"]()
        try:
            payload, _code = service.selfcheck()
        except GUIError as exc:
            status_label.setText(f"自检失败：{exc.message}")
            return
        status_label.setText(
            f"状态：{payload.get('status', '')} | 版本 {payload.get('version', '')}"
            f" | Python {payload.get('python', '')}"
            f" | 冻结态 {'是' if payload.get('frozen') else '否'}"
        )
        message = payload.get("message", "")
        if message:
            detail.setPlainText(str(message))
            detail.show()
        for rows in _sections(payload):
            table = widgets.rows_table(["字段", "值"], rows)
            layout.addWidget(table)
            tables.append(table)

    button.clicked.connect(on_click)
    return root


def _sections(payload):
    """payload → [rows]：规则集总览与参数来源各一张表。"""
    sections = []
    for ruleset in payload.get("rulesets") or []:
        sections.append(
            [
                ("规则集", ruleset.get("ruleset_id", "")),
                ("因素数", ruleset.get("factor_count", "")),
                ("已核对", ruleset.get("status_counts", {}).get("verified", "")),
                ("待核对", ruleset.get("pending_count", "")),
                ("待输入", ruleset.get("input_required_count", "")),
            ]
        )
    for source in payload.get("parameter_sources") or []:
        sections.append(
            [
                ("参数来源", source.get("ruleset_id", "")),
                ("文件", source.get("doc_code", "")),
                ("标题", source.get("doc_title", "")),
                ("发布方", source.get("issuer", "")),
                ("文号", source.get("doc_number", "")),
                ("实施", source.get("effective_from", "")),
                ("获取", source.get("fetched", "")),
            ]
        )
    return sections


def _clear(tables, layout):
    for table in tables:
        layout.removeWidget(table)
        table.deleteLater()
    del tables[:]
