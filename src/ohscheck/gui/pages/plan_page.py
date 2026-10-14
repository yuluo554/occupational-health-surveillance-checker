"""页签 2：岗位应检（岗位画像 JSON → 应检项目与周期推导）。"""

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

_HINT = '岗位画像 JSON，含 position_id / exam_date（精确日期）/ factors'


def build(service):
    """岗位应检页：粘贴/载入岗位画像 JSON，推导应检清单。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    input_row = QHBoxLayout()
    path_edit = QLineEdit()
    path_edit.setPlaceholderText(_HINT)
    input_row.addWidget(path_edit)
    browse = QPushButton("载入文件…")
    input_row.addWidget(browse)
    layout.addLayout(input_row)

    run = QPushButton("推导应检清单")
    layout.addWidget(run)

    status = QLabel("")
    layout.addWidget(status)

    pages = []
    container = QWidget()
    container_layout = QVBoxLayout(container)
    layout.addWidget(container)
    state = {"widgets": pages}

    def on_browse():
        selected, _ = QFileDialog.getOpenFileName(root, "选择岗位画像 JSON", "", "JSON (*.json)")
        if selected:
            path_edit.setText(selected)

    def on_run():
        _clear(state, container_layout)
        try:
            payload = service.plan(_profile_obj(path_edit.text()))
        except (GUIError, ValueError) as exc:
            message = exc.message if isinstance(exc, GUIError) else str(exc)
            status.setText(f"推导失败：{message}")
            return
        status.setText(
            f"规则集 {payload.get('ruleset_id', '')} | 岗位 {payload.get('position_id', '')}"
        )
        table = widgets.result_table(_scalars(payload))
        container_layout.addWidget(table)
        state["widgets"].append(table)
        tree = widgets.result_tree(_containers(payload))
        container_layout.addWidget(tree)
        state["widgets"].append(tree)

    browse.clicked.connect(on_browse)
    run.clicked.connect(on_run)
    return root


def _profile_obj(text):
    import json

    from ..service import GUIError

    stripped = text.strip()
    if not stripped:
        raise GUIError("请先粘贴岗位画像 JSON 或载入文件")
    if stripped.startswith("{"):
        return json.loads(stripped)
    with open(stripped, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _scalars(payload):
    return dict(widgets.scalar_rows(payload))


def _containers(payload):
    return {
        key: value
        for key, value in payload.items()
        if not widgets.is_scalar(value)
    }


def _clear(state, layout):
    for widget in state["widgets"]:
        layout.removeWidget(widget)
        widget.deleteLater()
    del state["widgets"][:]
