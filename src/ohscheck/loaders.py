"""JSON 载入与稳定序列化。

确定性纪律（NFR-4 / 决策 D-26）：
  * 金额/数值类一律 Decimal（JSON 载入 parse_float=Decimal），不用 float；
  * 落盘用 dumps_stable（sort_keys、固定分隔符、无空白漂移）+ write_bytes_lf；
  * 冻结产物不写时间戳；两次生成必须逐字节一致。

Python 3.8 兼容：不使用 Path.write_text(newline=)（那是 3.10+ 参数）。
"""

from __future__ import annotations

import json
from decimal import Decimal

from .errors import InputError


class _StableEncoder(json.JSONEncoder):
    def default(self, o):  # noqa: D102
        if isinstance(o, Decimal):
            # Decimal 序列化为字符串：既避免 float 精度漂移，也让字节输出确定
            return str(o)
        return json.JSONEncoder.default(self, o)


def loads(text):
    """载入 JSON 文本，浮点一律 Decimal。

    Raises:
        InputError: JSON 非法。
    """
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError as exc:
        raise InputError("JSON 解析失败：%s" % exc, reason="bad_json")


def load_path(path):
    """读盘并载入 JSON。

    Raises:
        InputError: 文件不存在 / 读盘失败 / JSON 非法。
    """
    import os

    if not os.path.isfile(path):
        raise InputError("文件不存在：%s" % path, reason="read_error")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise InputError("读盘失败 %s：%s" % (path, exc), reason="read_error")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("文件不是合法 UTF-8：%s（%s）" % (path, exc), reason="bad_json")
    return loads(text)


def dumps_stable(obj, indent=2):
    """确定性 JSON 文本（LF 行尾，无尾随空白）。"""
    text = json.dumps(
        obj,
        cls=_StableEncoder,
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        separators=(",", ": "),
    )
    return text.replace("\r\n", "\n") + "\n"


def write_bytes_lf(path, text):
    """以 LF 行尾写文本（3.8 兼容；不用 Path.write_text(newline=)）。"""
    if isinstance(text, str):
        data = text.replace("\r\n", "\n").encode("utf-8")
    else:
        data = text
    import os

    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as fh:
        fh.write(data)


def dump_stable(path, obj):
    """确定性落盘。"""
    write_bytes_lf(path, dumps_stable(obj))
