"""报告导出通路：把章节结构落成人读（Markdown）+ 机读（XLSX）+ 证据链。

两种格式消费**同一个** report_sections()（决策 D-33）——内容一致是结构性质。
"""

from __future__ import annotations

import os

from ..loaders import write_bytes_lf
from ..report.evidence import build_evidence, sha256_bytes, sha256_file, write_evidence
from ..report.markdown import render_markdown
from ..report.sections import report_sections
from ..report.xlsx import render_xlsx_bytes, render_xlsx_table

__all__ = [
    "export_report",
    "report_sections",
    "render_markdown",
    "render_xlsx_bytes",
    "render_xlsx_table",
]


def export_report(model, out_dir, ruleset_id="", ruleset_sha256="", input_paths=None):
    """导出报告三件套：report.md / report.xlsx / evidence.json。

    Args:
        model: ReportModel。
        out_dir: 输出目录。
        input_paths: 输入文件路径列表（挂指纹）。

    Returns:
        dict: {markdown, xlsx, evidence, sha256: {...}}
    """
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    sections = report_sections(model)
    md_text = render_markdown(model, sections)
    xlsx_bytes = render_xlsx_bytes(model, sections)

    md_path = os.path.join(out_dir, "report.md")
    xlsx_path = os.path.join(out_dir, "report.xlsx")
    write_bytes_lf(md_path, md_text)
    with open(xlsx_path, "wb") as fh:
        fh.write(xlsx_bytes)

    inputs = []
    for path in input_paths or []:
        if os.path.isfile(path):
            inputs.append({"path": os.path.basename(path), "sha256": sha256_file(path)})

    outputs = [
        {"path": "report.md", "sha256": sha256_bytes(md_text.encode("utf-8"))},
        {"path": "report.xlsx", "sha256": sha256_bytes(xlsx_bytes)},
    ]

    evidence_path = os.path.join(out_dir, "evidence.json")
    payload = build_evidence(
        ruleset_id=ruleset_id,
        ruleset_sha256=ruleset_sha256,
        inputs=inputs,
        outputs=outputs,
    )
    write_evidence(evidence_path, payload)

    return {
        "markdown": md_path,
        "xlsx": xlsx_path,
        "evidence": evidence_path,
        "sha256": {item["path"]: item["sha256"] for item in outputs},
    }
