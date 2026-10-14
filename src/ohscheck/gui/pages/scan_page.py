"""页签 4：批量扫描（档案目录 → 批量结果，可选上一轮目录对账）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..service import GUIError, Service
from . import widgets


def build(service):
    """批量扫描页：目录 + 可选 baseline 目录 → 结果分块。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    grid = QGridLayout()
    directory_edit = QLineEdit()
    baseline_edit = QLineEdit()
    grid.addWidget(QLabel("档案目录"), 0, 0)
    grid.addWidget(directory_edit, 0, 1)
    browse_dir = QPushButton("浏览…")
    grid.addWidget(browse_dir, 0, 2)
    grid.addWidget(QLabel("上一轮目录（可选）"), 1, 0)
    grid.addWidget(baseline_edit, 1, 1)
    browse_base = QPushButton("浏览…")
    grid.addWidget(browse_base, 1, 2)
    layout.addLayout(grid)

    run = QPushButton("开始扫描")
    layout.addWidget(run)

    status = QLabel("")
    layout.addWidget(status)

    container = QWidget()
    container_layout = QVBoxLayout(container)
    layout.addWidget(container)
    state = {"widgets": []}

    def _pick(edit):
        selected = QFileDialog.getExistingDirectory(root, "选择档案目录")
        if selected:
            edit.setText(selected)

    def on_run():
        _clear(state, container_layout)
        try:
            payload = service.scan(
                directory_edit.text().strip() or None,
                baseline_edit.text().strip() or None,
            )
        except GUIError as exc:
            status.setText(f"扫描失败：{exc.message}")
            return
        status.setText(
            f"共 {len(payload.get('items') or [])} 件"
            f" | 不符合 {_noncompliant(payload.get('items') or [])} 件"
            f" | 失败 {len(payload.get('failed') or [])} 件"
            f" | 待输入 {_input_required(payload.get('items') or [])} 件"
        )
        for label, block in _blocks(payload):
            header = QLabel(label)
            table = widgets.result_tree(block)
            container_layout.addWidget(header)
            container_layout.addWidget(table)
            state["widgets"].append(header)
            state["widgets"].append(table)

    browse_dir.clicked.connect(lambda: _pick(directory_edit))
    browse_base.clicked.connect(lambda: _pick(baseline_edit))
    run.clicked.connect(on_run)
    return root


_NONCOMPLIANT = ("partial", "non_compliant")
_PERIOD_INPUT = "input_required"


def _noncompliant(items):
    return _count_verdicts(items, _NONCOMPLIANT)


def _input_required(items):
    return sum(
        1
        for item in items
        if item.get("period_verdict") == _PERIOD_INPUT
    )


def _count_verdicts(items, verdicts):
    return sum(1 for item in items if item.get("verdict") in verdicts)


def _blocks(payload):
    blocks = [("概要", dict(widgets.scalar_rows(payload)))]
    failed = payload.get("failed") or []
    if failed:
        blocks.append(("失败件（未判定，单列）", failed))
    items = payload.get("items") or []
    if items:
        blocks.append(("逐件结果", items))
    reconcile = payload.get("reconcile")
    if reconcile:
        blocks.append(("跨轮对账", reconcile))
    baseline = payload.get("baseline")
    if baseline:
        blocks.append(("上一轮扫描", baseline))
    return blocks


def _clear(state, layout):
    for widget in state["widgets"]:
        layout.removeWidget(widget)
        widget.deleteLater()
    del state["widgets"][:]
