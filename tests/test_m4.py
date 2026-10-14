"""M4：内置基准（可证伪探活 + 未启用声明 + 门槛/运行时长 + 结构断言）。

对应 DoD：M4-1–M4-6（plan/05 §四 M4）。核心验收门：**基准会绿也会红**——
只会绿的基准是假基准（FR-E5 / plan/04 §9.3）。

探活纪律（HANDOFF-M4 §2.2）：全部用测试内夹具/临时目录（copytree 冻结产物再注入缺陷），
**不动** `data/benchmark/`（禁止事项：探活不得污染冻结产物）。
"""

from __future__ import annotations

import io
import json
import shutil
import sys

import pytest

from helpers import bench_dir

from ohscheck.benchmark.runner import SUITES, run_benchmarks
from ohscheck.errors import EXIT_NONCOMPLIANT, EXIT_OK, EXIT_USAGE
from ohscheck.loaders import dumps_stable, load_path


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


def _copy_bench(tmp_path):
    bench = tmp_path / "benchmark"
    shutil.copytree(bench_dir(), str(bench))
    return bench


def _suite(payload, name):
    return next(s for s in payload["suites"] if s["suite"] == name)


# ---------------- M4-3 可证伪探活：每套件注入缺陷 → 必须报未达标 ----------------


def test_liveness_matrix_corrupt_expect_plan(tmp_path):
    """matrix 探活：篡改期望应检清单（植入假项目）→ 样本驱动层必须报未达标。"""
    bench = _copy_bench(tmp_path)
    case_path = bench / "cases" / "case-2025.json"
    obj = load_path(str(case_path))
    expect_plan = obj["expect_plan"]
    factor = sorted(expect_plan)[0]
    first_exam = sorted(expect_plan[factor]["exams"])[0]
    expect_plan[factor]["exams"][first_exam] = ["SYN_LIVENESS_NOT_THERE"]
    case_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="matrix", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "注入缺陷后 matrix 仍报达标 → 探活失败"
    assert payload["passed"] is False
    suite = _suite(payload, "matrix")
    assert suite["correct"] < suite["samples"]


def test_liveness_matrix_rule_driven_layer(tmp_path):
    """matrix 探活（规则驱动层）：破坏引擎周期判定 → 规则驱动准确率必须掉下来。

    注入点在**引擎侧**（monkeypatch judge_period，用完即还原）：规则驱动层断言
    "上次检查 + N 月恰好到期"判 due/compliant——判定一律坏掉即红。
    runner 在套件函数内延迟 import，运行期打桩可达。
    """
    import ohscheck.engine.period as period_mod

    original = period_mod.judge_period

    def broken_judge(period, last, current):
        result = dict(original(period, last, current))
        result["verdict"] = "overdue"  # 引擎缺陷：一律判超期
        return result

    period_mod.judge_period = broken_judge
    try:
        code, payload, _err = _run(only="matrix", data_dir=None)
    finally:
        period_mod.judge_period = original
    assert code == EXIT_NONCOMPLIANT, "周期判定被破坏后 matrix 仍报达标 → 规则驱动层形同虚设"
    assert _suite(payload, "matrix")["rule_driven_accuracy"] < 1.0


def test_liveness_coverage_flip_truth(tmp_path):
    """coverage 探活：真值翻转（把"齐备"改成"缺一项"）→ 覆盖度对账必须报未达标。"""
    bench = _copy_bench(tmp_path)
    case_path = bench / "cases" / "case-2025.json"
    obj = load_path(str(case_path))
    target = next(rec for rec in obj["records"] if rec["expect"].get("should_be_clean"))
    target["expect"]["missing_items"] = ["SYN_LIVENESS_NOT_THERE"]
    case_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="coverage", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "真值翻转后 coverage 仍报达标 → 探活失败"
    suite = _suite(payload, "coverage")
    assert suite["correct"] < suite["samples"]


def test_liveness_compare_break_rule_difference(tmp_path):
    """compare 探活：把两版规则差异抹平（改期望 kind 为不存在的值）→ 必须报未达标。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    obj["compare_expect"]["SYN_FACTOR_ALPHA"] = "SYN_LIVENESS_KIND"  # 期望一个不存在的差异类型
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="compare", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "期望差异被破坏后 compare 仍报达标 → 探活失败"
    suite = _suite(payload, "compare")
    assert suite["correct"] < suite["samples"]


def test_liveness_compare_rulesets_actually_compared(tmp_path):
    """compare 探活（规则侧）：从 2025 夹具删掉一个共同因素 → 差异 kind 随之改变必红。

    证明 compare 真在读两套规则集，不是把期望抄一遍就算通过。
    （抹掉必检项不行：required_items_changed 期望依然命中——差异类型不随内容清空而变。）
    """
    bench = _copy_bench(tmp_path)
    rs_path = bench / "ruleset-2025.json"
    obj = load_path(str(rs_path))
    obj["factors"] = [f for f in obj["factors"] if f["factor_code"] != "SYN_FACTOR_ALPHA"]
    rs_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="compare", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "规则集差异被改变后 compare 仍报达标 → 探活失败"
    suite = _suite(payload, "compare")
    assert suite["correct"] < suite["samples"]
    suite = _suite(payload, "compare")
    assert suite["correct"] < suite["samples"]


def test_liveness_false_positive_clean_record_now_dirty(tmp_path):
    """false_positive 探活：把"应零命中"档案改成真缺项 → 误报数必须 > 0 → 未达标。"""
    bench = _copy_bench(tmp_path)
    case_path = bench / "cases" / "case-2025.json"
    obj = load_path(str(case_path))
    target = next(rec for rec in obj["records"] if rec["expect"].get("should_be_clean"))
    target["items"] = []  # 实检项目清空 → 引擎必报缺项 → "误报"出现
    case_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="false_positive", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "干净档案被弄脏后 false_positive 仍报达标 → 探活失败"
    suite = _suite(payload, "false_positive")
    assert suite["hits"] > 0


def test_liveness_runtime_threshold(tmp_path):
    """运行时长门槛探活：把 manifest 时长上限压到 0 秒 → 必须报未达标。

    证明 max_runtime_seconds 真被执行（写在 manifest 里 ≠ 锁在代码里，D-64 同族）。
    """
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    obj["benchmark_thresholds"]["max_runtime_seconds"] = 0.0
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "时长上限压到 0 后 bench 仍报达标 → 时长门槛未被执行"
    assert payload["runtime_ok"] is False
    assert payload["passed"] is False
    assert payload["elapsed_seconds"] > 0.0


# ---------------- M4-4 门槛随 manifest：缺失场景端到端 ----------------


def test_missing_threshold_block_end_to_end(tmp_path):
    """coverage_accuracy_min 缺失 → coverage 套件端到端退出码 2（D-24）。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    del obj["benchmark_thresholds"]["coverage_accuracy_min"]
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, _payload, err = _run(only="coverage", data_dir=str(tmp_path))
    assert code == EXIT_USAGE
    assert "门槛" in err


def test_runtime_threshold_missing_still_runs(tmp_path):
    """max_runtime_seconds 缺失 → 不回落默认值，也不误判：时长维度不判定（D-24）。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    del obj["benchmark_thresholds"]["max_runtime_seconds"]
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(data_dir=str(tmp_path))
    assert code == EXIT_OK
    assert "runtime_ok" not in payload
    assert "runtime_threshold_seconds" not in payload


# ---------------- M4-6 "未启用"套件如实声明 ----------------


def test_false_positive_zero_samples_declared_not_enabled(tmp_path):
    """误报对照集为空（无 should_be_clean 声明）→ not_enabled + 输出写明"未生成"，退出码 1。"""
    bench = _copy_bench(tmp_path)
    for name in ("case-2025.json", "case-2014.json"):
        case_path = bench / "cases" / name
        obj = load_path(str(case_path))
        for rec in obj["records"]:
            rec["expect"].pop("should_be_clean", None)
        case_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="false_positive", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT, "对照集为空仍报达标 = 假装覆盖（D-59）"
    suite = _suite(payload, "false_positive")
    assert suite["samples"] == 0
    assert suite["not_enabled"] is True
    assert suite["passed"] is False


def test_compare_zero_expectations_declared_not_enabled(tmp_path):
    """对照期望为空（manifest.compare_expect 删空）→ not_enabled + 写明"未生成"，退出码 1。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    obj["compare_expect"] = {}
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="compare", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT
    suite = _suite(payload, "compare")
    assert suite["samples"] == 0
    assert suite["not_enabled"] is True
    assert any("未生成" in n for n in suite["notes"])


def test_compare_single_ruleset_declared_not_enabled(tmp_path):
    """只登记一套规则集 → compare 未生成用例 → not_enabled（退出码 1，不假装通过）。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    obj["rulesets"] = [e for e in obj["rulesets"] if e["ruleset_id"] != "SYN-2014"]
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    code, payload, _err = _run(only="compare", data_dir=str(tmp_path))
    assert code == EXIT_NONCOMPLIANT
    suite = _suite(payload, "compare")
    assert suite["not_enabled"] is True
    assert suite["passed"] is False


def test_not_enabled_declaration_appears_in_text_output(tmp_path):
    """文本输出如实写明"该类用例未生成"（D-35：没查 ≠ 查了没问题）。"""
    bench = _copy_bench(tmp_path)
    manifest_path = bench / "manifest.json"
    obj = load_path(str(manifest_path))
    obj["compare_expect"] = {}
    manifest_path.write_bytes(dumps_stable(obj).encode("utf-8"))

    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = run_benchmarks(only="compare", data_dir=str(tmp_path), as_json=False)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    assert code == EXIT_NONCOMPLIANT
    assert "该类用例未生成" in out.getvalue()


# ---------------- M4-2 基准数据与生产数据分离：结构断言 ----------------


def test_benchmark_reads_nothing_outside_synthetic_fixtures():
    """基准数据面 = data/benchmark/ 合成夹具：合成标记 + SYNTHETIC- 结构护栏 + 无真实档案。

    D-51：基准验机制、不验国标内容——夹具必须自证合成（synthetic=true + SYNTHETIC-
    前缀 + issuer 为空），且基准用例目录不承载任何生产规则包/真值库文件。
    """
    import os

    bench = bench_dir()
    for name in ("ruleset-2014.json", "ruleset-2025.json"):
        obj = load_path(os.path.join(str(bench), name))
        assert obj.get("synthetic") is True, name
        assert obj["basis"]["doc_code"].startswith("SYNTHETIC-"), name
        assert obj["basis"]["issuer"] == "", name

    # 生产规则包与真值库不进基准目录（两套数据刻意分离，D-51）
    names = {n for _, _dirs, files in os.walk(str(bench)) for n in files}
    assert not any(n.startswith("GBZ188-") for n in names)
    assert "truth.json" not in names and "manifest.json.unreachable_cases" not in names


def test_bench_json_payload_carries_measured_metrics():
    """指标实测值随 JSON 结果下发（M4-5 的取数面）：正确率/误报数/运行时长。"""
    code, payload, _err = _run()
    assert code == EXIT_OK
    assert payload["passed"] is True
    assert payload["elapsed_seconds"] >= 0.0
    assert payload["runtime_ok"] is True
    for suite in payload["suites"]:
        if suite["suite"] == "false_positive":
            assert suite["hits"] == 0
        else:
            assert suite["accuracy"] == 1.0
            assert suite["samples"] > 0
            assert suite["correct"] == suite["samples"]
