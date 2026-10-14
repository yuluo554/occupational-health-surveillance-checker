"""页签公共渲染助手：结果字典 → QTableWidget/QTextEdit 的通用铺陈。

只做"数据形状 → 控件"的机械翻译，无任何判定逻辑。
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# 需要"整块可读文本"展示的长 JSON 值走文本框；其余进表格。
_TEXT_KEYS = ("message", "notes", "note", "reason", "basis")


def is_scalar(value):
    """渲染分派用：非容器即标量。"""
    return not isinstance(value, (dict, list))


def result_table(payload):
    """标量键值对 → 两列表格（键 / 值）。容器值交 result_tree。"""
    rows = [
        (key, value)
        for key, value in sorted(payload.items())
        if is_scalar(value)
    ]
    table = QTableWidget(len(rows), 2)
    table.setHorizontalHeaderLabels(["字段", "值"])
    for row, (key, value) in enumerate(rows):
        table.setItem(row, 0, QTableWidgetItem(str(key)))
        table.setItem(row, 1, QTableWidgetItem(_fmt(value)))
    table.resizeColumnsToContents()
    return table


def result_tree(payload):
    """容器值 → 展开表格（路径 / 值），列表带序号路径。"""
    rows = list(_flatten("", payload))
    table = QTableWidget(len(rows), 2)
    table.setHorizontalHeaderLabels(["路径", "值"])
    for row, (path, value) in enumerate(rows):
        table.setItem(row, 0, QTableWidgetItem(path))
        table.setItem(row, 1, QTableWidgetItem(_fmt(value)))
    table.resizeColumnsToContents()
    return table


def result_text(text):
    """长文本 → 只读文本框。"""
    box = QPlainTextEdit()
    box.setPlainText(text)
    box.setReadOnly(True)
    font = QFont("Consolas")
    font.setStyleHint(QFont.Monospace)
    box.setFont(font)
    return box


def scalar_rows(payload):
    """dict → [(key, scalar_value)]（页签自拼表头时用）。"""
    return [
        (key, value)
        for key, value in sorted(payload.items())
        if is_scalar(value)
    ]


def rows_table(header_labels, rows):
    """给定表头与二维行数据 → 表格（供列表型结果用）。"""
    table = QTableWidget(len(rows), len(header_labels))
    table.setHorizontalHeaderLabels(list(header_labels))
    for row, record in enumerate(rows):
        for col, value in enumerate(record):
            table.setItem(row, col, QTableWidgetItem(_fmt(value)))
    table.resizeColumnsToContents()
    return table


def vbox(widgets):
    """纵排布局容器（页签根件的标准拼装）。"""
    page = QWidget()
    layout = QVBoxLayout(page)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return page


def _flatten(prefix, value):
    """容器展平为 (路径, 标量值) 行；空容器显示为 <空>。"""
    if isinstance(value, dict):
        if not value:
            yield (prefix or "<root>", "<空对象>")
            return
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            for item in _flatten(child, value[key]):
                yield item
    elif isinstance(value, list):
        if not value:
            yield (prefix or "<root>", "<空列表>")
            return
        for idx, item in enumerate(value):
            child = f"{prefix}[{idx}]"
            for entry in _flatten(child, item):
                yield entry
    else:
        yield (prefix, value)


def _fmt(value):
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "<无>"
    return str(value)
