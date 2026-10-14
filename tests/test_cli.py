"""CLI 退出码三语义 + 扫描失败隔离 + 报告导出。

对应 DoD：M0-8（退出码锁进测试）、M0-9。
退出码契约（plan/03 §七）：0 = 无不符合 / 1 = 检出不符合 / 2 = 用法或坐标错误 / 3 = 缺可选依赖。
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from helpers import make_factor, make_record, make_temp_data_dir, write_json

from ohscheck.cli import main


def _run(argv):
    """跑 CLI，返回 (exit_code, stdout, stderr)。"""
    out = io.StringIO()
    err = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


@pytest.fixture()
def data_env(tmp_path):
    """可被 CLI 使用的具名 data/ 目录（含 rules/manifest.json）。"""
    factors = [
        make_factor(code="T_FACTOR", fid="5.1.0", months=12, required=("A1", "A2")),
    ]
    root = tmp_path / "data"
    root.mkdir()
    return make_temp_data_dir(str(root), factors=factors)


# ---------------- 退出码 0 ----------------


def test_version_exit_0():
    code, out, _err = _run(["version"])
    assert code == 0
    assert "0.1.0" in out


def test_selfcheck_exit_0_on_production_data():
    code, out, _err = _run(["selfcheck", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["status"] == "OK"
    assert payload["pending_total"] > 0  # M0 初态全部 pending，如实呈现


def test_bench_exit_0_on_synthetic_fixtures():
    code, out, _err = _run(["bench"])
    assert code == 0, out
    assert "达标" in out


def test_plan_exit_0_on_verified_synthetic_ruleset(data_env, tmp_path):
    pos = {
        "position_id": "POS-1",
        "exam_date": "2026-09-15",
        "factors": [{"factor_code": "T_FACTOR"}],
    }
    path = str(tmp_path / "pos.json")
    write_json(path, pos)
    code, out, _err = _run(["plan", path, "--data-dir", data_env, "--json"])
    assert code == 0, out
    payload = json.loads(out)
    assert payload["ruleset_id"] == "SYN-TEST"


# ---------------- 退出码 1：检出不符合 ----------------


def test_check_exit_1_on_noncompliant(data_env, tmp_path):
    rec = make_record(items=("A1",), exam_type="pre_placement")  # 缺 A2 → partial
    path = str(tmp_path / "rec.json")
    write_json(path, rec)
    code, out, _err = _run(["check", path, "--data-dir", data_env, "--json"])
    assert code == 1, out
    assert json.loads(out)["verdict"] == "partial"


def test_check_exit_0_on_compliant(data_env, tmp_path):
    rec = make_record(items=("A1", "A2"), exam_type="pre_placement")
    path = str(tmp_path / "rec.json")
    write_json(path, rec)
    code, out, _err = _run(["check", path, "--data-dir", data_env, "--json"])
    assert code == 0, out
    assert json.loads(out)["verdict"] == "compliant"


def test_scan_exit_1_on_noncompliant(data_env, tmp_path):
    scan_dir = tmp_path / "records"
    scan_dir.mkdir()
    write_json(str(scan_dir / "r1.json"), make_record(items=("A1",), exam_type="pre_placement"))
    code, out, _err = _run(["scan", str(scan_dir), "--data-dir", data_env, "--json"])
    assert code == 1, out
    assert json.loads(out)["stats"]["total"] == 1


def test_check_uses_record_last_exam_date_for_period(data_env, tmp_path):
    """回归：单件 check 必须用档案自身的 last_exam_date 做周期判定。

    实测抓到的 bug：CLI 单件通路丢掉了 last_exam_date → 所有周期判定退化成
    no_baseline → FR-B4（周期合规）在 check 通路**不可达**（假绿）。
    """
    rec = make_record(
        items=("A1", "A2"), exam_type="periodic",
        exam_date="2026-09-15", last_exam_date="2024-01-01",  # 12 月周期 → 超期
    )
    path = str(tmp_path / "rec.json")
    write_json(path, rec)
    code, out, _err = _run(["check", path, "--data-dir", data_env, "--json"])
    payload = json.loads(out)
    assert payload["period_verdict"] == "overdue", payload
    assert code == 1  # 超期 → 计入不符合


def test_check_period_due_day_counts_as_compliant_via_cli(data_env, tmp_path):
    rec = make_record(
        items=("A1", "A2"), exam_type="periodic",
        exam_date="2026-09-15", last_exam_date="2025-09-15",  # 恰好到期
    )
    path = str(tmp_path / "rec.json")
    write_json(path, rec)
    code, out, _err = _run(["check", path, "--data-dir", data_env, "--json"])
    payload = json.loads(out)
    assert payload["period_verdict"] == "due"
    assert code == 0


def test_check_without_baseline_does_not_report_overdue(data_env, tmp_path):
    rec = make_record(items=("A1", "A2"), exam_type="periodic", exam_date="2026-09-15")
    path = str(tmp_path / "rec.json")
    write_json(path, rec)
    code, out, _err = _run(["check", path, "--data-dir", data_env, "--json"])
    assert json.loads(out)["period_verdict"] == "no_baseline"
    assert code == 0


# ---------------- 退出码 2：用法/输入/坐标错误 ----------------


def test_check_exit_2_on_missing_file():
    code, _out, err = _run(["check", "no-such-file.json"])
    assert code == 2
    assert "错误" in err


def test_check_exit_2_on_bad_json(data_env, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    code, _out, _err = _run(["check", str(bad), "--data-dir", data_env])
    assert code == 2


def test_plan_exit_2_when_gate_blocks_pending(tmp_path):
    """引用到未核对条目 → 门控拦截 → 退出码 2（决策 D-12）。

    M1 起生产包是**真实混合态**：第 5–7 章（化学/粉尘/物理）明细已 verified，
    第 8–9 章（生物/特殊作业）只落了因素身份、明细仍 pending。用它验
    "引用到 pending 即拦截"，同时反证"只看整包 status"会漏。
    """
    pos = {
        "position_id": "POS-P",
        "exam_date": "2026-09-15",
        "factors": [{"factor_code": "GBZ188-8.1"}],  # 布鲁氏菌：明细 pending
    }
    path = str(tmp_path / "pos.json")
    write_json(path, pos)
    code, _out, err = _run(["plan", path])
    assert code == 2
    assert "门控" in err
    assert "8.1" in err  # 拦截信息须点出未核对条目坐标


def test_plan_exit_0_on_verified_real_factor(tmp_path):
    """第 5–7 章已核对因素 → plan 放行、退出码 0（M1 混态的另一侧）。"""
    pos = {
        "position_id": "POS-BENZENE",
        "exam_date": "2026-09-15",
        "factors": [{"factor_code": "GBZ188-5.19"}],  # 苯
    }
    path = str(tmp_path / "pos.json")
    write_json(path, pos)
    code, out, _err = _run(["plan", path, "--json"])
    assert code == 0, out
    payload = json.loads(out)
    assert payload["ruleset_id"] == "GBZ188-2025"
    plan = payload["factors"][0]
    assert plan["exams"]["periodic"]["required_items"]  # 必检项非空（真实数据）


def test_plan_exit_2_on_ambiguous_year(data_env, tmp_path):
    """只给年度且含切口日 → 退出码 2（决策 D-11，宁报错不猜）。"""
    pos = {
        "position_id": "POS-P",
        "exam_date": "2026",
        "factors": [{"factor_code": "T_FACTOR"}],
    }
    path = str(tmp_path / "pos.json")
    write_json(path, pos)
    code, _out, _err = _run(["plan", path, "--data-dir", data_env])
    assert code == 2


def test_bench_exit_2_on_unknown_suite():
    """--only 传未知名 → 退出码 2（决策 D-25，不许静默跳过）。"""
    code, _out, err = _run(["bench", "--only", "not_a_suite"])
    assert code == 2
    assert "未知基准套件" in err


def test_no_command_exit_2():
    code, _out, _err = _run([])
    assert code == 2


def test_selfcheck_exit_2_when_data_dir_missing():
    code, out, _err = _run(["selfcheck", "--data-dir", "no-such-dir"])
    assert code == 2


def test_scan_missing_directory_exits_2(data_env):
    code, _out, _err = _run(["scan", "no-such-dir", "--data-dir", data_env])
    assert code == 2


# ---------------- 退出码 3：缺可选依赖 ----------------


def test_gui_without_pyside6_exits_3(monkeypatch):
    """GUI extra 未安装 → 退出码 3（惰性导入契约，决策 D-38）。

    用 __import__ 打桩让 PySide6 抛 ImportError——本机装了 extra 也能测。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PySide6" or name.startswith("PySide6."):
            raise ImportError("no PySide6 (stubbed)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for mod in list(sys.modules):
        if mod.startswith("ohscheck.gui"):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    code, _out, err = _run(["gui"])
    assert code == 3, err
    assert "PySide6" in err


# ---------------- 失败件 ≠ 违规（决策 D-21）----------------


def test_scan_failure_is_isolated_and_does_not_become_violation(data_env, tmp_path):
    """坏件混入：整批继续，坏件单列原因码，**不改变退出码**。"""
    scan_dir = tmp_path / "records"
    scan_dir.mkdir()
    write_json(str(scan_dir / "good.json"), make_record(items=("A1", "A2"), exam_type="pre_placement"))
    (scan_dir / "broken.json").write_bytes(b"{oops")

    code, out, _err = _run(["scan", str(scan_dir), "--data-dir", data_env, "--json"])
    assert code == 0, out  # 无不符合项 → 退出码 0，尽管有失败件
    payload = json.loads(out)
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["reason"] in ("bad_json", "schema_invalid")
    assert payload["stats"]["total"] == 1


def test_oversized_file_is_isolated_with_reason(data_env, tmp_path):
    """超大输入走安全阀，记 container_too_large，不整体读入、不中断整批。"""
    scan_dir = tmp_path / "records"
    scan_dir.mkdir()
    write_json(str(scan_dir / "ok.json"), make_record(items=("A1", "A2"), exam_type="pre_placement"))
    big = scan_dir / "big.json"
    big.write_bytes(b"[" + b"0" * 4096 + b"]")

    code, out, _err = _run([
        "scan", str(scan_dir), "--data-dir", data_env, "--json",
    ])
    # 默认上限 2MiB，4KB 不会超限；改用小上限验证安全阀需直接调引擎
    assert code == 0, out

    from ohscheck.engine.scan import scan_directory

    def provider(factor_code, exam_date, record):
        raise AssertionError("超限件不应进入判定路径")

    result = scan_directory(str(scan_dir), provider, max_bytes=16)
    reasons = {f.reason for f in result.failed}
    assert "container_too_large" in reasons


# ---------------- 报告导出 ----------------


def test_report_export_creates_three_artifacts(data_env, tmp_path):
    out_dir = tmp_path / "out"
    rec = make_record(items=("A1",), exam_type="pre_placement")
    rec_path = str(tmp_path / "rec.json")
    write_json(rec_path, rec)
    scan_dir = tmp_path / "records"
    scan_dir.mkdir()
    write_json(str(scan_dir / "r1.json"), rec)

    code, out, _err = _run([
        "report", str(out_dir), "--directory", str(scan_dir),
        "--record", rec_path, "--data-dir", data_env,
        "--generated-at", "2026-10-14T00:00:00", "--json",
    ])
    assert code == 0, out
    assert os.path.isfile(str(out_dir / "report.md"))
    assert os.path.isfile(str(out_dir / "report.xlsx"))
    assert os.path.isfile(str(out_dir / "evidence.json"))


# ---------------- 编码守卫（决策 D-39）----------------


def test_ensure_utf8_stdio_reconfigures_cp1252_stream():
    """cp1252 管道不因非 ASCII 输出崩（本机即可复现，不必等 CI）。"""
    from ohscheck.cli import _ensure_utf8_stdio

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    original = sys.stdout
    sys.stdout = stream
    try:
        _ensure_utf8_stdio()
        stream.write("中文输出\n")
        stream.flush()
    finally:
        sys.stdout = original
    assert stream.encoding.lower().replace("-", "") in ("utf8", "utf_8")


def test_ensure_utf8_stdio_leaves_utf8_stream_alone():
    from ohscheck.cli import _ensure_utf8_stdio

    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    original = sys.stdout
    sys.stdout = stream
    try:
        _ensure_utf8_stdio()
    finally:
        sys.stdout = original
    assert stream.encoding.lower().replace("-", "") in ("utf8", "utf_8")
