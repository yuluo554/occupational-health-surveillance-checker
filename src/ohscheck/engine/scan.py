"""批量扫描（FR-D1/D2/D5）。

两条硬纪律（决策 D-21）：
  ① **失败件 ≠ 违规**：坏 JSON/超大输入是**未判定**，记 failed + 原因码，
     **不改变退出码**（退出码仍由"是否检出不符合"决定）。
  ② **失败隔离**：单件异常**不中断整批**；超大输入有安全阀，**不整体读入**。

分派点唯一（决策 D-32）：scan 与 check 走**同一个** engine.coverage.check_record。
"""

from __future__ import annotations

import os

from ..errors import (
    OhsCheckError,
    REASON_BAD_JSON,
    REASON_CONTAINER_TOO_LARGE,
    REASON_READ_ERROR,
)
from ..loaders import loads
from ..model import HealthRecord, VERDICT_FAILED, VERDICT_LABELS, CoverageResult

DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 单件上限 2 MiB（安全阀）


class FailedItem:
    """未判定的档案（原因码单列，绝不静默吞掉）。"""

    __slots__ = ("path", "reason", "message")

    def __init__(self, path, reason, message):
        self.path = path
        self.reason = reason
        self.message = message

    def as_dict(self):
        return {
            "path": self.path,
            "reason": self.reason,
            "message": self.message,
            "verdict": VERDICT_FAILED,
            "verdict_label": VERDICT_LABELS[VERDICT_FAILED],
        }


class ScanResult:
    """批量扫描结果。"""

    __slots__ = ("items", "failed", "stats")

    def __init__(self, items=None, failed=None):
        self.items = list(items or [])
        self.failed = list(failed or [])
        self.stats = {}

    @property
    def noncompliant(self):
        from ..model import NONCOMPLIANT_VERDICTS

        return [r for r in self.items if r.verdict in NONCOMPLIANT_VERDICTS]

    @staticmethod
    def _empty_bucket(factor_code, position_id):
        """一个统计桶：非 pass 结论计数的可复算载体（M3-4）。"""
        return {
            "factor_code": factor_code,
            "position_id": position_id,
            "examined": 0,
            "compliant": 0,
            "noncompliant": 0,
            "not_applicable": 0,
            "unknown": 0,
        }

    def compute_stats(self):
        """群体统计（FR-D4 / M3-4）：按因素与岗位两维汇总，可由明细逐项复算。

        可复算背书：`detail_sha256` = 逐件 (record_id, factor_code, position_id,
        exam_type, verdict) 确定性序列化后再哈希——明细变 → 哈希变；
        统计与明细不一致时 `tests/test_m3.py` 的对账测试必挂。
        """
        from ..model import NONCOMPLIANT_VERDICTS
        from ..loaders import dumps_stable
        from ..report.evidence import sha256_bytes

        by_factor = {}
        by_position = {}
        for rec in self.items:
            verdict = rec.verdict
            if verdict in NONCOMPLIANT_VERDICTS:
                kind = "noncompliant"
            elif verdict == "compliant":
                kind = "compliant"
            elif verdict == "not_applicable":
                kind = "not_applicable"
            else:
                kind = "unknown"

            bucket = by_factor.setdefault(
                rec.factor_code,
                self._empty_bucket(rec.factor_code, ""),
            )
            bucket["examined"] += 1
            bucket[kind] += 1

            p_bucket = by_position.setdefault(
                rec.position_id,
                self._empty_bucket("", rec.position_id),
            )
            p_bucket["examined"] += 1
            p_bucket[kind] += 1

        # 明细哈希：把"sum(明细) == 统计"从测试期断言升级为产物自带字段
        detail_lines = [
            dumps_stable(
                {
                    "record_id": rec.record_id,
                    "factor_code": rec.factor_code,
                    "position_id": rec.position_id,
                    "exam_type": rec.exam_type,
                    "verdict": rec.verdict,
                }
            )
            for rec in self.items
        ]
        self.stats = {
            "total": len(self.items),
            "failed": len(self.failed),
            "detail_sha256": sha256_bytes("\n".join(detail_lines)),
            "by_factor": [by_factor[k] for k in sorted(by_factor)],
            "by_position": [by_position[k] for k in sorted(by_position)],
        }
        return self.stats

    def as_dict(self):
        return {
            "items": [r.as_dict() for r in self.items],
            "failed": [f.as_dict() for f in self.failed],
            "stats": self.stats,
        }


def iter_record_files(directory, suffix=".json"):
    """枚举目录下的档案文件（排序保证确定性）。"""
    out = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for name in sorted(files):
            if name.lower().endswith(suffix):
                out.append(os.path.join(root, name))
    return out


def _load_record_file(path, max_bytes):
    """读单件并解析为 HealthRecord；任何失败只抛异常由调用方隔离。"""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise OhsCheckError("读盘失败：%s" % exc, reason=REASON_READ_ERROR)
    if size > max_bytes:
        raise OhsCheckError(
            "文件 %d 字节超过单件上限 %d 字节（安全阀，不整体读入）" % (size, max_bytes),
            reason=REASON_CONTAINER_TOO_LARGE,
        )
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise OhsCheckError("读盘失败：%s" % exc, reason=REASON_READ_ERROR)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OhsCheckError("文件不是合法 UTF-8：%s" % exc, reason=REASON_BAD_JSON)

    try:
        obj = loads(text)
    except OhsCheckError:
        raise
    # 允许 {record: {...}} 包装形式
    if isinstance(obj, dict) and "record_id" not in obj and isinstance(obj.get("record"), dict):
        obj = obj["record"]
    return HealthRecord.from_dict(obj)


def scan_directory(directory, plan_provider, alias_map=None, max_bytes=DEFAULT_MAX_BYTES):
    """批量扫描目录，逐件核查，失败件隔离。

    Args:
        directory: 档案目录。
        plan_provider: 可调用对象 (factor_code, exam_date) → PlanResult（按锚定版本推导）。
        alias_map: 显式别名表。
        max_bytes: 单件字节上限（安全阀）。

    Returns:
        ScanResult。

    Raises:
        OhsCheckError: 目录不存在。
    """
    from .coverage import check_record

    if not os.path.isdir(directory):
        raise OhsCheckError("目录不存在：%s" % directory, reason=REASON_READ_ERROR)

    result = ScanResult()
    for path in iter_record_files(directory):
        rel = os.path.relpath(path, directory)
        try:
            record = _load_record_file(path, max_bytes)
        except OhsCheckError as exc:
            result.failed.append(FailedItem(rel, exc.reason, exc.message))
            continue
        except Exception as exc:  # noqa: BLE001 - 单件异常不中断整批（决策 D-21）
            result.failed.append(FailedItem(rel, REASON_BAD_JSON, str(exc)))
            continue

        try:
            plan_result, last_exam_date = plan_provider(record.factor_code, record.exam_date, record)
            coverage = check_record(
                record, plan_result, alias_map=alias_map, last_exam_date=last_exam_date
            )
        except OhsCheckError as exc:
            # 门控拦截 / 待输入 → 未判定，不改变退出码
            result.failed.append(FailedItem(rel, exc.reason, exc.message))
            continue
        except Exception as exc:  # noqa: BLE001
            result.failed.append(FailedItem(rel, REASON_BAD_JSON, str(exc)))
            continue

        if coverage.verdict == VERDICT_FAILED or coverage.failed_reason:
            result.failed.append(
                FailedItem(rel, coverage.failed_reason or REASON_BAD_JSON, coverage.failed_message)
            )
            continue
        result.items.append(coverage)

    result.compute_stats()
    return result


def scan_paths(paths, plan_provider, alias_map=None, max_bytes=DEFAULT_MAX_BYTES):
    """按清单批量扫描（与目录扫描同一分派点）。"""
    from .coverage import check_record

    result = ScanResult()
    for path in sorted(paths):
        rel = os.path.basename(path)
        try:
            record = _load_record_file(path, max_bytes)
            plan_result, last_exam_date = plan_provider(record.factor_code, record.exam_date, record)
            coverage = check_record(
                record, plan_result, alias_map=alias_map, last_exam_date=last_exam_date
            )
        except OhsCheckError as exc:
            result.failed.append(FailedItem(rel, exc.reason, exc.message))
            continue
        except Exception as exc:  # noqa: BLE001
            result.failed.append(FailedItem(rel, REASON_BAD_JSON, str(exc)))
            continue
        if coverage.failed_reason:
            result.failed.append(
                FailedItem(rel, coverage.failed_reason, coverage.failed_message)
            )
            continue
        result.items.append(coverage)
    result.compute_stats()
    return result


def has_noncompliant(scan_result):
    """批量结果是否检出不符合（退出码 1 的判据；失败件不算，决策 D-21）。"""
    return len(scan_result.noncompliant) > 0
