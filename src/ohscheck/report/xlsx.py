"""最小 OOXML（XLSX）writer——自写，零第三方依赖。

为什么不用 openpyxl（决策 D-06，**实测过的坑**）：
  openpyxl 的 save() 会把**当前时间**写进 zip 条目与文档属性，
  同秒两次才一致、跨秒必漂 → 破坏"机读产物逐字节可复现"（NFR-4 / FR-F6）。
自写 writer 用 ZIP_STORED + 固定 create_system=0 + 固定 date_time + 固定 external_attr，
"同输入 → 同字节"是结构性质。

无外链（决策 D-34）：只写内联字符串，不产生 external 关系、不写 w:hyperlink。
"""

from __future__ import annotations

import io
import zipfile

from .sections import report_sections

# 固定时间戳（1980-01-01 00:00:00，zip 纪元）
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_STORED = zipfile.ZIP_STORED


def _escape(text):
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _col_name(index):
    """0 → A, 25 → Z, 26 → AA。"""
    name = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _shared_strings_index(strings):
    table = {}
    for text in strings:
        if text not in table:
            table[text] = len(table)
    return table


def _sheet_rows(sections):
    """把章节结构摊成二维行（单一渲染源的产物之一）。"""
    rows = []
    for section in sections:
        rows.append(["§%s %s" % (section.number, section.title)])
        for para in section.paragraphs:
            rows.append([para])
        for table in section.tables:
            if table.title:
                rows.append([table.title])
            if table.headers:
                rows.append(list(table.headers))
            for row in table.rows:
                cells = [("" if c is None else str(c)) for c in row]
                while len(cells) < len(table.headers):
                    cells.append("")
                rows.append(cells[: len(table.headers)])
        for note in section.notes:
            rows.append(["注：" + note])
        rows.append([])
    return rows


def _cell_xml(row_idx, col_idx, value, strings_index):
    if value is None or value == "":
        return ""
    ref = "%s%d" % (_col_name(col_idx), row_idx)
    idx = strings_index[value]
    return '<c r="%s" t="s"><v>%d</v></c>' % (ref, idx)


def _sheet_xml(rows):
    strings = []
    for row in rows:
        for cell in row:
            if cell:
                strings.append(cell)
    strings_index = _shared_strings_index(strings)
    width = max((len(r) for r in rows), default=1)

    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        # CT_Worksheet 的子元素次序固定：dimension 必须在 sheetData 之前
        '<dimension ref="A1:%s%d"/>' % (_col_name(width - 1), max(len(rows), 1)),
        "<sheetData>",
    ]
    for r_i, row in enumerate(rows, start=1):
        out.append('<row r="%d">' % r_i)
        for c_i, cell in enumerate(row):
            out.append(_cell_xml(r_i, c_i, cell, strings_index))
        out.append("</row>")
    out.append("</sheetData>")
    out.append("</worksheet>")
    return "\n".join(out), strings


def _shared_strings_xml(strings):
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="%d" uniqueCount="%d">'
        % (len(strings), len(strings)),
    ]
    for text in strings:
        out.append("<si><t xml:space=\"preserve\">%s</t></si>" % _escape(text))
    out.append("</sst>")
    return "\n".join(out)


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="核查报告" sheetId="1" r:id="rId1"/></sheets>'
    "</workbook>"
)

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
    "</Relationships>"
)


def _write_entry(zf, name, data):
    """写入一个 zip 条目，时间戳与宿主标识全部固定。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
    info.compress_type = _STORED
    info.create_system = 0  # 0 = MS-DOS：跨平台字节一致
    info.external_attr = 0
    zf.writestr(info, data)


def render_xlsx_bytes(model, sections=None):
    """渲染为 XLSX 字节（同输入 → 同字节）。"""
    sections = sections if sections is not None else report_sections(model)
    rows = _sheet_rows(sections)
    sheet_xml, strings = _sheet_xml(rows)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", _STORED) as zf:
        _write_entry(zf, "[Content_Types].xml", _CONTENT_TYPES)
        _write_entry(zf, "_rels/.rels", _ROOT_RELS)
        _write_entry(zf, "xl/workbook.xml", _WORKBOOK)
        _write_entry(zf, "xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        _write_entry(zf, "xl/worksheets/sheet1.xml", sheet_xml)
        _write_entry(zf, "xl/sharedStrings.xml", _shared_strings_xml(strings))
    return buffer.getvalue()


def render_xlsx_table(model, sections=None):
    """把章节结构摊成二维表（供测试做两格式逐项对等断言）。"""
    sections = sections if sections is not None else report_sections(model)
    return _sheet_rows(sections)
