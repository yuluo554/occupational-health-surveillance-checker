"""规则包载入：从 data/rules/ 读 manifest 与各版本规则集。

载入即校验（schema.validate_ruleset / validate_manifest），坏包在入口就被拦下。
"""

from __future__ import annotations

import hashlib
import os

from .. import paths
from ..errors import InputError
from ..loaders import load_path
from .schema import validate_manifest, validate_ruleset

MANIFEST_NAME = "manifest.json"


class Ruleset:
    """一份已校验的规则集（不可变视图）。"""

    __slots__ = ("obj", "ruleset_id", "basis", "factors", "_by_code", "_by_id", "path")

    def __init__(self, obj, path=None):
        self.obj = obj
        self.path = path
        self.ruleset_id = obj["ruleset_id"]
        self.basis = obj["basis"]
        self.factors = obj["factors"]
        self._by_code = {}
        self._by_id = {}
        for factor in self.factors:
            self._by_code[factor["factor_code"]] = factor
            self._by_id[factor["factor_id"]] = factor

    def factor(self, code):
        return self._by_code.get(code)

    def has_factor(self, code):
        return code in self._by_code

    @property
    def factor_codes(self):
        return sorted(self._by_code)

    def status_counts(self):
        counts = {"verified": 0, "pending": 0, "input_required": 0}
        for factor in self.factors:
            for status in self._iter_statuses(factor):
                counts[status] = counts.get(status, 0) + 1
        return counts

    @staticmethod
    def _iter_statuses(factor):
        yield factor["status"]
        yield factor["eligibility"]["status"]
        yield factor["period"]["status"]
        for disease in factor.get("target_diseases") or []:
            yield disease["status"]
        for key in ("pre_placement", "periodic", "post_placement", "emergency"):
            block = factor["examinations"][key]
            yield block["status"]
            for group in ("required_items", "supplementary_items", "optional_items"):
                for item in block.get(group) or []:
                    yield item["status"]


class Manifest:
    """manifest 视图。"""

    __slots__ = ("obj", "path", "cutover", "thresholds", "ruleset_files")

    def __init__(self, obj, path=None):
        self.obj = obj
        self.path = path
        self.cutover = obj["cutover"]
        self.thresholds = obj["benchmark_thresholds"]
        self.ruleset_files = {}
        for entry in obj["rulesets"]:
            self.ruleset_files[entry["ruleset_id"]] = entry.get("file")

    @property
    def cutover_date_text(self):
        return str(self.cutover["date"])

    def ruleset_ids(self):
        return [entry["ruleset_id"] for entry in self.obj["rulesets"]]

    def entry(self, ruleset_id):
        for item in self.obj["rulesets"]:
            if item["ruleset_id"] == ruleset_id:
                return item
        return None


def rules_dir(data_dir=None):
    """data/rules/ 目录；不存在返回 None。"""
    return paths.data_subdir("rules", explicit=data_dir)


def load_manifest(data_dir=None):
    """载入并校验 manifest。

    Raises:
        InputError: data/rules/ 缺失、manifest 缺失或校验失败。
    """
    root = rules_dir(data_dir)
    if root is None:
        raise InputError(
            "未找到 data/rules/ 目录。请先运行 python tools/gen_rulesets.py 生成规则包。",
            reason="read_error",
        )
    path = os.path.join(root, MANIFEST_NAME)
    obj = load_path(path)
    validate_manifest(obj)
    return Manifest(obj, path)


def load_ruleset(ruleset_id, data_dir=None, manifest=None):
    """按 ruleset_id 载入并校验规则集。

    Raises:
        InputError: 未在 manifest 登记 / 文件缺失 / 校验失败。
    """
    manifest = manifest or load_manifest(data_dir)
    entry = manifest.entry(ruleset_id)
    if entry is None:
        raise InputError(
            "manifest 未登记规则集 %r（已登记：%s）"
            % (ruleset_id, ", ".join(manifest.ruleset_ids())),
            reason="unknown_factor",
        )
    filename = entry.get("file")
    if not filename:
        raise InputError("manifest 中 %r 缺少 file 字段" % ruleset_id)
    root = rules_dir(data_dir)
    path = os.path.join(root, filename)
    obj = load_path(path)
    validate_ruleset(obj)
    if obj["ruleset_id"] != ruleset_id:
        raise InputError(
            "规则集文件 %s 的 ruleset_id 为 %r，与请求的 %r 不一致"
            % (filename, obj["ruleset_id"], ruleset_id)
        )
    return Ruleset(obj, path)


def load_all_rulesets(data_dir=None, manifest=None):
    """载入 manifest 登记的全部规则集。"""
    manifest = manifest or load_manifest(data_dir)
    return {rid: load_ruleset(rid, data_dir, manifest) for rid in manifest.ruleset_ids()}


def file_sha256(path):
    """文件 sha256（小写十六进制）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
