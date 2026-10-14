"""页签 6：报告导出（plan/record/directory 任意组合 → Markdown+XLSX+证据链）。"""

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

_GENERATED_AT_HINT = "报告生成时间（ISO 格式精确到秒；注入以保持可复现）"


def build(service):
    """报告导出页：输入路径 + 生成时间 → 三件套落盘路径。"""
    root = QWidget()
    layout = QVBoxLayout(root)

    grid = QGridLayout()
    out_edit = QLineEdit()
    position_edit = QLineEdit()
    record_edit = QLineEdit()
    directory_edit = QLineEdit()
    baseline_edit = QLineEdit()
    generated_edit = QLineEdit()
    generated_edit.setPlaceholderText(_GENERATED_AT_HINT)

    browse_out = QPushButton("浏览…")
    browse_position = QPushButton("浏览…")
    browse_record = QPushButton("浏览…")
    browse_directory = QPushButton("浏览…")
    browse_baseline = QPushButton("浏览…")

    rows = [
        ("输出目录*", out_edit, browse_out, "dir"),
        ("岗位画像 JSON", position_edit, browse_position, "json"),
        ("单件档案 JSON", record_edit, browse_record, "json"),
        ("档案目录", directory_edit, browse_directory, "dir"),
        ("上一轮目录", baseline_edit, browse_baseline, "dir"),
        ("生成时间", generated_edit, None, None),
    ]
    for row, (label, edit, browse, kind) in enumerate(rows):
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(edit, row, 1)
        if browse is not None:
            grid.addWidget(browse, row, 2)
        if browse is not None:
            browse.clicked.connect(lambda _=False, e=edit, k=kind: _pick(root, e, k))
    layout.addLayout(grid)

    run = QPushButton("导出报告")
    layout.addWidget(run)

    status = QLabel("")
    layout.addWidget(status)

    detail = widgets.result_text("")
    layout.addWidget(detail)
    state = {"first": True}

    def on_run():
        detail.setPlainText("")
        try:
            paths_out = service.export_report(
                out_dir=out_edit.text().strip() or None,
                generated_at=generated_edit.text().strip() or None,
                position_path=position_edit.text().strip() or None,
                record_path=record_edit.text().strip() or None,
                directory=directory_edit.text().strip() or None,
                baseline=baseline_edit.text().strip() or None,
            )
        except GUIError as exc:
            status.setText(f"导出失败：{exc.message}")
            return
        status.setText("报告已导出（Markdown + XLSX + 证据链）")
        lines = []
        for key in sorted(paths_out):
            value = paths_out[key]
            if isinstance(value, dict):
                for sub in sorted(value):
                    lines.append(f"{key}.{sub} = {value[sub]}")
            else:
                lines.append(f"{key} = {value}")
        detail.setPlainText("\n".join(lines))
        state["first"] = False

    run.clicked.connect(on_run)
    return root


def _pick(parent, edit, kind):
    if kind == "dir":
        selected = QFileDialog.getExistingDirectory(parent, "选择目录")
    else:
        selected, _ = QFileDialog.getOpenFileName(parent, "选择 JSON 文件", "", "JSON (*.json)")
    if selected:
        edit.setText(selected)
