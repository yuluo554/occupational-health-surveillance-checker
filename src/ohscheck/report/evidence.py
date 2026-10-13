"""证据链（FR-F1/F2）：文件指纹 + 报告自指纹。

"报告被改动即可检出"：evidence.json 的 outputs[] 含报告**自身** sha256。
generated_at 不写入本文件——保持产物逐字节可复现（决策 D-42）。
"""

from __future__ import annotations

import hashlib
import os

from ..loaders import dumps_stable


def sha256_bytes(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_evidence(ruleset_id="", ruleset_sha256="", inputs=None, outputs=None):
    """构造 evidence.json 内容。

    Args:
        inputs: [{path, sha256}] 本地文件引用与指纹。
        outputs: [{path, sha256}] **含报告自身**。
    """
    return {
        "ruleset": {"ruleset_id": ruleset_id, "sha256": ruleset_sha256},
        "inputs": list(inputs or []),
        "outputs": list(outputs or []),
        "generated_at": None,
        "note": "生成时间不写入本文件，以保全逐字节可复现；报告被改动即与 outputs[].sha256 不符。",
    }


def write_evidence(path, payload):
    """确定性落盘 evidence.json。"""
    from ..loaders import write_bytes_lf

    write_bytes_lf(path, dumps_stable(payload))


def verify_evidence(evidence_path, root=None):
    """核验证据链：逐项复算 outputs/inputs 的 sha256。

    Returns:
        dict: {ok: bool, checked: int, mismatched: [path], missing: [path]}
    """
    from ..loaders import load_path

    payload = load_path(evidence_path)
    base = root or os.path.dirname(os.path.abspath(evidence_path))
    mismatched = []
    missing = []
    checked = 0
    for group in ("inputs", "outputs"):
        for item in payload.get(group) or []:
            rel = item.get("path")
            if not rel:
                continue
            target = rel if os.path.isabs(rel) else os.path.join(base, rel)
            if not os.path.isfile(target):
                missing.append(rel)
                continue
            checked += 1
            if sha256_file(target) != item.get("sha256"):
                mismatched.append(rel)
    return {
        "ok": not mismatched and not missing,
        "checked": checked,
        "mismatched": mismatched,
        "missing": missing,
    }
