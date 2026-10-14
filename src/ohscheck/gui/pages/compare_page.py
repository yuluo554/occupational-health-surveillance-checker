"""页签 5：版本对照（双规则集差异对照）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..service import GUIError, Service
from . import widgets


def build(service):
    """版本对照页：新旧 ruleset_id 下拉 → 差异清单。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    grid = QGridLayout()
    combo_old = QComboBox()
    combo_new = QComboBox()
    grid.addWidget(QLabel("旧版"), 0, 0)
    grid.addWidget(combo_old, 0, 1)
    grid.addWidget(QLabel("新版"), 1, 0)
    grid.addWidget(combo_new, 1, 1)
    layout.addLayout(grid)

    refresh = QPushButton("载入可用规则集")
    run = QPushButton("对照")
    layout.addWidget(refresh)
    layout.addWidget(run)

    status = QLabel("")
    layout.addWidget(status)

    container = QWidget()
    container_layout = QVBoxLayout(container)
    layout.addWidget(container)
    state = {"widgets": []}

    def on_refresh():
        combo_old.clear()
        combo_new.clear()
        for ruleset_id in service.ruleset_ids():
            combo_old.addItem(ruleset_id)
            combo_new.addItem(ruleset_id)
        if combo_new.count() > 0:
            combo_new.setCurrentIndex(_last_index(combo_new))
        status.setText(f"可用规则集 {combo_old.count()} 个")

    def on_run():
        _clear(state, container_layout)
        id_a = combo_old.currentText()
        id_b = combo_new.currentText()
        if not id_a or not id_b:
            status.setText("请先载入可用规则集")
            return
        try:
            payload = service.compare(id_a, id_b)
        except GUIError as exc:
            status.setText(f"对照失败：{exc.message}")
            return
        status.setText(
            f"对照 {id_a} → {id_b} | 差异 {len(payload.get('differences') or [])} 处"
        )
        for label, block in _blocks(payload):
            header = QLabel(label)
            table = widgets.result_tree(block)
            container_layout.addWidget(header)
            container_layout.addWidget(table)
            state["widgets"].append(header)
            state["widgets"].append(table)

    refresh.clicked.connect(on_refresh)
    run.clicked.connect(on_run)
    return root


def _last_index(combo):
    """末项下标（倒序枚举取数，页内不写算术）。"""
    index = 0
    for current in range(combo.count()):
        index = current
    return index


def _blocks(payload):
    blocks = [("概要", dict(widgets.scalar_rows(payload)))]
    for key in ("differences", "summary"):
        value = payload.get(key)
        if value:
            blocks.append((key, value))
    return blocks


def _clear(state, layout):
    for widget in state["widgets"]:
        layout.removeWidget(widget)
        widget.deleteLater()
    del state["widgets"][:]
