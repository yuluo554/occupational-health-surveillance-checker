"""基准：四套件达标、门槛随 manifest 下发、可证伪探活、退出码三语义。

对应 DoD：M0-9（基准可跑）、M4-1–M4-4（骨架期先把机制锁死）。
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from helpers import bench_dir

from ohscheck.benchmark.runner import SUITES, run_benchmarks
from ohscheck.errors import EXIT_NONCOMPLIANT, EXIT_OK, EXIT_USAGE, MissingThresholdError


def _run(only=None, data_dir=None):
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = run_benchmarks(only=only, data_dir=data_dir, as_json=True)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    payload = json.loads(out.getvalue()) if out.getvalue().strip().startswith("{") else None
    return code, payload, err.getvalue()


# ---------------- 四套件全达标 ----------------


def test_all_suites_pass_on_synthetic_fixtures():
    code, payload, err = _run()
    assert code == EXIT_OK, (err, payload)
    assert payload["passed"] is True
    assert {s["suite"] for s in payload["suites"]} == set(SUITES)


def test_each_suite_individually_reaches_threshold():
    for name in SUITES:
        code, payload, _err = _run(only=name)
        assert code == EXIT_OK, name
        assert payload["suites"][0]["passed"] is True, name


def test_false_positive_suite_reads_clean_declaration_only():
    """误报对照集**只读**真值库的"应零命中"声明，不自选考卷（FR-E4）。"""
    code, payload, _err = _run(only="false_positive")
    assert code == EXIT_OK
    suite = payload["suites"][0]
    assert suite["hits"] == 0
    assert suite["samples"] > 0  # 确实有被判的干净档案，不是"什么都没查"


def test_matrix_reports_rule_driven_layer():
    """样本驱动 + 规则驱动两层（plan/04 §9.2）。"""
    code, payload, _err = _run(only="matrix")
    assert code == EXIT_OK
    suite = payload["suites"][0]
    assert suite["samples"] > 0
    assert suite["rule_driven_samples"] > 0


# ---------------- 门槛随 manifest 下发（决策 D-24）----------------


def test_thresholds_come_from_manifest():
    code, payload, _err = _run()
    assert code == EXIT_OK
    for suite in payload["suites"]:
        assert "threshold" in suite and suite["threshold"] is not None


def test_missing_threshold_is_config_error_not_default(tmp_path):
    """门槛缺失 → 退出码 2，**不得回落代码默认值**（决策 D-24）。"""
    import shutil

    bench = tmp_path / "benchmark"
    shutil.copytree(bench_dir(), str(bench))
    manifest_path = bench / "manifest.json"

    from ohscheck.loaders import dumps_stable, load_path

    obj = load_path(str(manifest_path))
    del obj["benchmark_thresholds"]["matrix_accuracy_min"]
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, _payload, err = _run(only="matrix", data_dir=str(tmp_path))
    assert code == EXIT_USAGE
    assert "门槛" in err


# ---------------- 可证伪探活（FR-E5 / 决策 D-27 同族）----------------


def test_benchmark_is_falsifiable_by_corrupting_truth(tmp_path):
    """给真值注入缺陷 → 基准**必须**报未达标。

    不配探活的"基准全绿"可能只是"基准什么都没查"。
    """
    import shutil

    from ohscheck.loaders import dumps_stable, load_path

    bench = tmp_path / "benchmark"
    shutil.copytree(bench_dir(), str(bench))

    # 篡改 case-2025 的第一条真值：把"齐备"改成"缺一项"→ 引擎必报不一致
    case_path = bench / "cases" / "case-2025.json"
    obj = load_path(str(case_path))
    target = None
    for rec in obj["records"]:
        if rec["expect"].get("should_be_clean"):
            target = rec
            break
    assert target is not None
    target["expect"]["missing_items"] = ["SYN_ITEM_NOT_THERE"]  # 注入假期望
    case_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "注入缺陷后基准仍报达标 → 探活失败（基准不可证伪）"
    assert payload["passed"] is False


def test_corrupting_rule_period_breaks_matrix_suite(tmp_path):
    """改规则表周期 → 规则驱动层应能察觉端点变化（基准真的在读规则表）。"""
    import shutil

    from ohscheck.loaders import dumps_stable, load_path

    bench = tmp_path / "benchmark"
    shutil.copytree(bench_dir(), str(bench))

    rs_path = bench / "ruleset-2025.json"
    obj = load_path(str(rs_path))
    obj["factors"][0]["period"]["value"] = 999  # 荒谬周期
    rs_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, _payload, _err = _run(only="coverage", data_dir=str(tmp_path))
    # 周期改成 999 个月 → 原期望 overdue 的用例不再 overdue → 覆盖度对账应不过
    assert code == EXIT_NONCOMPLIANT


# ---------------- 退出码三语义（决策 D-25）----------------


def test_unknown_suite_exits_2():
    code, _payload, err = _run(only="not_a_suite")
    assert code == EXIT_USAGE
    assert "未知基准套件" in err


def test_empty_only_exits_2():
    code, _payload, _err = _run(only=",")
    assert code == EXIT_USAGE


def test_missing_benchmark_dir_exits_2(tmp_path):
    code, _payload, err = _run(data_dir=str(tmp_path))
    assert code == EXIT_USAGE
    assert "benchmark" in err


def test_partial_run_does_not_judge_untested_metrics():
    """--only 部分运行时不判定未测指标（否则把"没测"误报成"未达标"）。"""
    code, payload, _err = _run(only="matrix")
    assert code == EXIT_OK
    assert len(payload["suites"]) == 1
    assert payload["suites"][0]["suite"] == "matrix"
