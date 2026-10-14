"""页签 3：档案核查（单件监护档案 JSON → 覆盖度核查）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..service import GUIError, Service
from . import widgets


def build(service):
    """档案核查页：粘贴/载入单件档案，渲染覆盖度判定。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    input_row = QHBoxLayout()
    path_edit = QLineEdit()
    path_edit.setPlaceholderText("监护档案 JSON 路径，或直接粘贴档案 JSON")
    input_row.addWidget(path_edit)
    browse = QPushButton("载入文件…")
    input_row.addWidget(browse)
    layout.addLayout(input_row)

    run = QPushButton("核查该档案")
    layout.addWidget(run)

    status = QLabel("")
    layout.addWidget(status)

    container = QWidget()
    container_layout = QVBoxLayout(container)
    layout.addWidget(container)
    state = {"widgets": []}

    def on_browse():
        selected, _ = QFileDialog.getOpenFileName(root, "选择监护档案 JSON", "", "JSON (*.json)")
        if selected:
            path_edit.setText(selected)

    def on_run():
        _clear(state, container_layout)
        try:
            payload = service.check(_record_obj(path_edit.text()))
        except (GUIError, ValueError) as exc:
            message = exc.message if isinstance(exc, GUIError) else str(exc)
            status.setText(f"核查失败：{message}")
            return
        status.setText(
            f"档案 {payload.get('record_id', '')} | 判定 {payload.get('verdict', '')}"
            f" | 周期 {payload.get('period_verdict', '')}"
        )
        for label, block in _blocks(payload):
            header = QLabel(label)
            container_layout.addWidget(header)
            table = widgets.result_tree(block) if not widgets.is_scalar(block) else None
            if table is None:
                container_layout.addWidget(widgets.result_text(str(block)))
            else:
                container_layout.addWidget(table)
            state["widgets"].append(header)
            state["widgets"].append(table or header)

    browse.clicked.connect(on_browse)
    run.clicked.connect(on_run)
    return root


def _blocks(payload):
    """核查结果分块：判定摘要 + 缺项 + 补充项 + 待输入。"""
    blocks = [("摘要", dict(widgets.scalar_rows(payload)))]
    for key in ("missing_items", "extra_items", "missing_inputs"):
        value = payload.get(key)
        if value:
            blocks.append((key, value))
    exams = payload.get("exams") or {}
    for exam_type in sorted(exams):
        blocks.append((f"检查时点 {exam_type}", exams[exam_type]))
    return blocks


def _record_obj(text):
    import json

    stripped = text.strip()
    if not stripped:
        raise GUIError("请先粘贴监护档案 JSON 或载入文件")
    if stripped.startswith("{"):
        return json.loads(stripped)
    with open(stripped, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _clear(state, layout):
    for widget in state["widgets"]:
        layout.removeWidget(widget)
        widget.deleteLater()
    del state["widgets"][:]
