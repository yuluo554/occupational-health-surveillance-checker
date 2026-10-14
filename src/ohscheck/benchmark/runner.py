"""基准运行器（FR-E1–E6）。

四套件：
    matrix          监护矩阵（样本驱动 + 规则驱动两层）
    coverage        覆盖度四态判定（样本驱动，植入真值）
    compare         双版本对照（结构一致）
    false_positive  误报对照集（**只读**真值库的"应零命中"声明，不自选考卷）

退出码三语义（决策 D-25，锁进测试）：
    0 达标 / 1 未达标 / 2 输入、坐标或用例名错误
"""

from __future__ import annotations

import os
import sys

from ..errors import EXIT_NONCOMPLIANT, EXIT_OK, EXIT_USAGE, MissingThresholdError, OhsCheckError
from .cases import compare_expected, is_clean_expect, observed_is_clean

SUITES = ("matrix", "coverage", "compare", "false_positive")

# 每个套件对应的门槛键（**全部来自 manifest**，代码零默认值）
SUITE_THRESHOLDS = {
    "matrix": ("matrix_accuracy_min",),
    "coverage": ("coverage_accuracy_min",),
    "compare": ("compare_accuracy_min",),
    "false_positive": ("false_positive_max",),
}


class BenchEnv:
    """基准运行环境（加载合成夹具，不碰生产规则包）。"""

    __slots__ = ("root", "manifest", "rulesets", "cases", "thresholds")

    def __init__(self, root):
        from ..loaders import load_path
        from ..rules.loader import Ruleset
        from ..rules.schema import validate_manifest, validate_ruleset

        self.root = root
        manifest_path = os.path.join(root, "manifest.json")
        manifest_obj = load_path(manifest_path)
        validate_manifest(manifest_obj)
        from ..rules.loader import Manifest

        self.manifest = Manifest(manifest_obj, manifest_path)
        self.thresholds = manifest_obj["benchmark_thresholds"]

        self.rulesets = {}
        for rid in self.manifest.ruleset_ids():
            entry = self.manifest.entry(rid)
            path = os.path.join(root, entry["file"])
            obj = load_path(path)
            validate_ruleset(obj)
            self.rulesets[rid] = Ruleset(obj, path)

        self.cases = []
        cases_dir = os.path.join(root, "cases")
        if os.path.isdir(cases_dir):
            for name in sorted(os.listdir(cases_dir)):
                if name.endswith(".json"):
                    self.cases.append(load_path(os.path.join(cases_dir, name)))

    def threshold(self, key):
        """取门槛；缺失即报配置错误（决策 D-24，**不回落代码默认值**）。"""
        if key not in self.thresholds:
            raise MissingThresholdError(key)
        return self.thresholds[key]


def _resolve_bench_dir(data_dir=None):
    from .. import paths

    root = paths.data_subdir("benchmark", explicit=data_dir)
    if root is None:
        raise OhsCheckError(
            "未找到 data/benchmark/ 合成夹具目录。请先运行 python tools/gen_cases.py 生成。",
            reason="read_error",
        )
    return root


# ---------------- 套件 ----------------


def _exposure_ref(record_obj, factor_code):
    """构造因素引用，带上记录里的接触水平（阈值型适用性判定用）。

    接触水平缺失 → FactorRef.exposure_value=None → 适用性 input_required
    （决策 D-13：绝不静默取默认值）。
    """
    from ..model import FactorRef, parse_decimal

    exposure = record_obj.get("exposure") or {}
    value = parse_decimal(exposure.get("value"), "exposure.value") if exposure else None
    return FactorRef(factor_code, exposure_value=value, exposure_unit=exposure.get("unit"))


def suite_matrix(env):
    """监护矩阵：样本驱动（真值对账）+ 规则驱动（从规则表推导端点）。"""
    from ..engine.matrix import compute_plan, expected_items
    from ..model import FactorRef, PositionProfile
    from ..rules.gate import effective_ruleset

    total = 0
    correct = 0
    details = []

    # ---- 样本驱动：逐用例对账应检清单 ----
    for case in env.cases:
        expect_plan = case.get("expect_plan") or {}
        ruleset = env.rulesets[case["ruleset_id"]]
        factor_codes = sorted(expect_plan)
        eff = effective_ruleset(ruleset, "bench", required_factor_ids=factor_codes)
        profile = PositionProfile(
            position_id=case.get("case_id", "BENCH"),
            exam_date=case["position"]["exam_date"],
            factors=[FactorRef(code) for code in factor_codes],
        )
        plan = compute_plan(profile, eff)
        for code, exp in sorted(expect_plan.items()):
            total += 1
            ok = True
            for exam_type, items in sorted((exp.get("exams") or {}).items()):
                got = expected_items(plan, code, exam_type)
                if sorted(got) != sorted(items):
                    ok = False
                    details.append(
                        {"case": case["case_id"], "factor": code, "exam": exam_type,
                         "expected": sorted(items), "got": sorted(got)}
                    )
            if ok:
                correct += 1

    # ---- 规则驱动：不读真值库，只从规则表推导端点 ----
    # 起点日期同样不硬编码：取 manifest 的切口日（数据），保证"代码零字面量"。
    rule_checked = 0
    rule_ok = 0
    anchor = env.manifest.cutover_date_text
    for rid, ruleset in sorted(env.rulesets.items()):
        for factor in ruleset.factors:
            period = factor["period"]
            if period.get("kind") != "months":
                continue
            months = period["value"]
            # 端点：恰好到期日 = 上次检查 + N 月；断言引擎在那里判"到期（合规）"
            from ..engine.period import add_months, judge_period

            last = anchor
            due = add_months(last, months)
            rule_checked += 1
            got = judge_period(period, last, str(due))["verdict"]
            if got in ("due", "compliant"):
                rule_ok += 1

    accuracy = (correct / total) if total else 0.0
    rule_accuracy = (rule_ok / rule_checked) if rule_checked else 1.0
    return {
        "suite": "matrix",
        "samples": total,
        "correct": correct,
        "accuracy": accuracy,
        "rule_driven_samples": rule_checked,
        "rule_driven_accuracy": rule_accuracy,
        "threshold_key": "matrix_accuracy_min",
        "threshold": env.threshold("matrix_accuracy_min"),
        "details": details[:20],
        "passed": accuracy >= env.threshold("matrix_accuracy_min")
        and rule_accuracy >= env.threshold("matrix_accuracy_min"),
    }


def suite_coverage(env):
    """覆盖度判定：样本驱动，逐档对账植入真值。"""
    from ..engine.coverage import check_record
    from ..engine.matrix import compute_plan
    from ..model import FactorRef, HealthRecord, PositionProfile
    from ..rules.gate import effective_ruleset

    total = 0
    correct = 0
    details = []

    for case in env.cases:
        ruleset = env.rulesets[case["ruleset_id"]]
        for record_obj in case.get("records") or []:
            expect = record_obj.get("expect") or {}
            factor_code = record_obj["factor_code"]
            eff = effective_ruleset(ruleset, "bench", required_factor_ids=[factor_code])
            profile = PositionProfile(
                position_id=record_obj.get("position_id") or case["case_id"],
                exam_date=record_obj["exam_date"],
                factors=[_exposure_ref(record_obj, factor_code)],
            )
            plan = compute_plan(profile, eff)
            record = HealthRecord.from_dict(record_obj)
            result = check_record(
                record, plan, alias_map=None, last_exam_date=record_obj.get("last_exam_date")
            )
            total += 1
            outcome = compare_expected(result, expect)
            if outcome["ok"]:
                correct += 1
            else:
                details.append(
                    {"case": case["case_id"], "record": record.record_id, "outcome": outcome}
                )

    accuracy = (correct / total) if total else 0.0
    return {
        "suite": "coverage",
        "samples": total,
        "correct": correct,
        "accuracy": accuracy,
        "threshold_key": "coverage_accuracy_min",
        "threshold": env.threshold("coverage_accuracy_min"),
        "details": details[:20],
        "passed": accuracy >= env.threshold("coverage_accuracy_min"),
    }


def suite_compare(env):
    """双版本对照：同因素在两版下的应检差异与真值一致。"""
    from ..engine.compare import compare_rulesets
    from ..rules.gate import effective_ruleset

    expectations = env.manifest.obj.get("compare_expect") or {}
    ids = env.manifest.ruleset_ids()
    if len(ids) < 2:
        return {
            "suite": "compare",
            "samples": 0,
            "correct": 0,
            "accuracy": 1.0,
            "threshold_key": "compare_accuracy_min",
            "threshold": env.threshold("compare_accuracy_min"),
            "skipped": True,
            "notes": ["夹具只登记了 %d 套规则集，双版本对照套件未生成用例。" % len(ids)],
            "passed": True,
        }

    eff_a = effective_ruleset(env.rulesets[ids[0]], "compare")
    eff_b = effective_ruleset(env.rulesets[ids[1]], "compare")
    report = compare_rulesets(eff_a, eff_b)

    total = 0
    correct = 0
    details = []
    for code, want_kind in sorted(expectations.items()):
        total += 1
        # 差异条目的 key 有两种形态：因素级（"CODE"）与时点级（"CODE/exam_type"），
        # 故按"因素前缀"匹配，而不是精确相等。
        got_kinds = {
            e.kind for e in report.entries if e.key == code or e.key.startswith(code + "/")
        }
        if want_kind in got_kinds:
            correct += 1
        else:
            details.append({"key": code, "expected_kind": want_kind, "got": sorted(got_kinds)})

    accuracy = (correct / total) if total else 1.0
    return {
        "suite": "compare",
        "samples": total,
        "correct": correct,
        "accuracy": accuracy,
        "threshold_key": "compare_accuracy_min",
        "threshold": env.threshold("compare_accuracy_min"),
        "details": details,
        "notes": report.notes,
        "passed": accuracy >= env.threshold("compare_accuracy_min"),
    }


def suite_false_positive(env):
    """误报对照集：**只读**真值库声明的"应零命中"档案，不自选考卷。"""
    from ..engine.coverage import check_record
    from ..engine.matrix import compute_plan
    from ..model import FactorRef, HealthRecord, PositionProfile
    from ..rules.gate import effective_ruleset

    total = 0
    hits = 0
    details = []

    for case in env.cases:
        ruleset = env.rulesets[case["ruleset_id"]]
        for record_obj in case.get("records") or []:
            expect = record_obj.get("expect") or {}
            if not is_clean_expect(expect):
                continue  # 只读声明，不自选
            total += 1
            factor_code = record_obj["factor_code"]
            eff = effective_ruleset(ruleset, "bench", required_factor_ids=[factor_code])
            profile = PositionProfile(
                position_id=record_obj.get("position_id") or case["case_id"],
                exam_date=record_obj["exam_date"],
                factors=[_exposure_ref(record_obj, factor_code)],
            )
            plan = compute_plan(profile, eff)
            record = HealthRecord.from_dict(record_obj)
            result = check_record(
                record, plan, alias_map=None, last_exam_date=record_obj.get("last_exam_date")
            )
            if not observed_is_clean(result):
                hits += 1
                details.append(
                    {"case": case["case_id"], "record": record.record_id,
                     "verdict": result.verdict, "missing": result.missing_items,
                     "period": result.period_verdict}
                )

    max_allowed = env.threshold("false_positive_max")
    return {
        "suite": "false_positive",
        "samples": total,
        "hits": hits,
        "threshold_key": "false_positive_max",
        "threshold": max_allowed,
        "details": details,
        "passed": hits <= max_allowed,
    }


SUITE_FUNCS = {
    "matrix": suite_matrix,
    "coverage": suite_coverage,
    "compare": suite_compare,
    "false_positive": suite_false_positive,
}


def _select(only):
    if only is None:
        return list(SUITES)
    names = []
    for name in str(only).split(","):
        name = name.strip()
        if not name:
            continue
        if name not in SUITE_FUNCS:
            raise OhsCheckError(
                "未知基准套件 %r（可用：%s）" % (name, ", ".join(SUITES)), reason="unknown_suite"
            )
        names.append(name)
    if not names:
        raise OhsCheckError("--only 未给出有效套件名", reason="unknown_suite")
    return names


def run_benchmarks(only=None, data_dir=None, as_json=False, quiet=False):
    """运行基准；返回退出码（0 达标 / 1 未达标 / 2 用法或配置错误）。"""
    try:
        names = _select(only)
        env = BenchEnv(_resolve_bench_dir(data_dir))
        results = [SUITE_FUNCS[name](env) for name in names]
    except OhsCheckError as exc:
        sys.stderr.write("错误：%s\n原因码：%s\n" % (exc.message, exc.reason))
        return EXIT_USAGE

    passed = all(r["passed"] for r in results)
    payload = {"suites": results, "passed": passed}

    if as_json:
        from ..loaders import dumps_stable

        sys.stdout.write(dumps_stable(payload))
    elif not quiet:
        for result in results:
            if result["suite"] == "false_positive":
                line = "%-16s 用例 %d，误报 %d（上限 %s）→ %s" % (
                    result["suite"], result["samples"], result["hits"],
                    result["threshold"], "达标" if result["passed"] else "未达标",
                )
            else:
                line = "%-16s 用例 %d，正确 %d，准确率 %.4f（门槛 %s）→ %s" % (
                    result["suite"], result["samples"], result["correct"],
                    result["accuracy"], result["threshold"],
                    "达标" if result["passed"] else "未达标",
                )
            sys.stdout.write(line + "\n")

    return EXIT_OK if passed else EXIT_NONCOMPLIANT
