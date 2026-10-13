"""报告导出：人读（Markdown）+ 机读（XLSX）+ 证据链。

关键设计（决策 D-33 / D-34 / D-35 / D-42）：
  * **单一渲染源**：markdown 与 xlsx 都消费 report_sections() 返回的同一章节结构，
    于是"两格式内容一致"是**结构性质**，不是人工比对；
  * **机读产物逐字节可复现**：自写最小 OOXML writer（ZIP_STORED + 固定时间戳）；
  * **无外链**：URL 只作纯文本落在参数来源块；
  * **"未启用"章节显式写出**，不留空。
"""

from __future__ import annotations

from .sections import Section, build_model, report_sections

__all__ = ["Section", "build_model", "report_sections"]
