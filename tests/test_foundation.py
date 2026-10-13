"""基础层：数据定位四分支、行尾/字节确定性。

对应 DoD：M0-4（再生成逐字节一致）、M0-11（paths 四分支）、M0-12（CR 守门）。
"""

from __future__ import annotations

import os

import pytest

from helpers import bench_dir, data_dir, make_ruleset, repo_root

from ohscheck import loaders, paths
from ohscheck.rules.loader import file_sha256


# ---------------- paths 四分支（M0-11）----------------


def test_explicit_beats_everything(monkeypatch, tmp_path):
    explicit = tmp_path / "data"
    explicit.mkdir()
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "other"))
    assert paths.find_data_dir(str(explicit)) == str(explicit)


def test_env_var_used_when_no_explicit(monkeypatch, tmp_path):
    env_dir = tmp_path / "data"
    env_dir.mkdir()
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(env_dir))
    assert paths.find_data_dir() == str(env_dir)


def test_source_mode_finds_repo_data(monkeypatch):
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)
    assert paths.find_data_dir() == data_dir()


def test_source_candidates_are_upward_from_package():
    """源码态候选必须自包位置上溯到含 pyproject.toml 的仓库根（决策 D-36）。"""
    candidates = paths.source_data_candidates()
    assert data_dir() in candidates
    assert paths.find_data_dir() is not None


def test_frozen_candidates_layout_order(monkeypatch, tmp_path):
    """冻结态候选顺序：_MEIPASS/data → exe/_internal/data → exe/data。"""
    exe = tmp_path / "dist" / "app"
    exe.mkdir(parents=True)
    meipass = tmp_path / "meipass"
    meipass.mkdir()
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe / "app.exe"))
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(meipass), raising=False)
    candidates = paths.frozen_data_candidates()
    assert candidates[0] == os.path.join(str(meipass), "data")
    assert candidates[1] == os.path.join(str(exe), "_internal", "data")
    assert candidates[2] == os.path.join(str(exe), "data")


def test_data_dir_is_inside():
    """冻结态自检判据：commonpath == container（决策 D-37）。"""
    assert paths.data_dir_is_inside("/a/b/data", "/a/b") is True
    assert paths.data_dir_is_inside("/a/c/data", "/a/b") is False


def test_data_dir_is_inside_handles_cross_drive():
    """跨盘符不应抛异常（os.path.commonpath 会 ValueError）。"""
    result = paths.data_dir_is_inside("C:\\x\\data", "D:\\y")
    assert result is False


# ---------------- 确定性：再生成逐字节一致（M0-4）----------------


def test_frozen_rulesets_regenerate_byte_identical():
    """规则包为生成器冻结产物；再生成必须逐字节一致（决策 D-26）。"""
    import subprocess
    import sys

    root = repo_root()
    before = {
        name: file_sha256(os.path.join(data_dir(), "rules", name))
        for name in ("manifest.json", "ruleset-2014.json", "ruleset-2025.json")
    }
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "gen_rulesets.py"), "--check"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert "FROZEN_RULESETS_OK" in out
    after = {
        name: file_sha256(os.path.join(data_dir(), "rules", name))
        for name in ("manifest.json", "ruleset-2014.json", "ruleset-2025.json")
    }
    assert before == after


def test_frozen_cases_regenerate_byte_identical():
    """合成夹具同样为冻结产物；再生成必须逐字节一致。"""
    import subprocess
    import sys

    root = repo_root()
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "gen_cases.py"), "--check"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert "FROZEN_CASES_OK" in out


def test_frozen_files_have_no_cr():
    """冻结件出现 CR 即失败（M0-12，跨机器复现性破坏的守门）。"""
    offenders = []
    for base, _dirs, files in os.walk(data_dir()):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                raw = fh.read()
            if b"\r" in raw:
                offenders.append(os.path.relpath(path, data_dir()))
    assert not offenders, "冻结件含 CR（行尾未归一）：%s" % offenders


def test_dumps_stable_is_deterministic_and_lf():
    obj = {"b": 1, "a": [2, 3], "s": "中文"}
    first = loaders.dumps_stable(obj)
    second = loaders.dumps_stable(obj)
    assert first == second
    assert "\r" not in first
    assert first.endswith("\n")


def test_write_bytes_lf_normalizes_crlf(tmp_path):
    path = tmp_path / "out.txt"
    loaders.write_bytes_lf(str(path), "a\r\nb\n")
    with open(str(path), "rb") as fh:
        assert fh.read() == b"a\nb\n"


def test_loads_uses_decimal_for_floats():
    """浮点一律 Decimal（避免 float repr 漂移，NFR-4）。"""
    from decimal import Decimal

    got = loaders.loads('{"v": 0.1}')
    assert isinstance(got["v"], Decimal)
    assert got["v"] == Decimal("0.1")


def test_dump_stable_serializes_decimal_as_string():
    from decimal import Decimal

    text = loaders.dumps_stable({"v": Decimal("12.50")})
    assert '"12.50"' in text


# ---------------- 合成夹具的 provenance 护栏 ----------------


def test_benchmark_rulesets_are_marked_synthetic():
    """基准夹具必须标 synthetic，且出处带合成前缀（数据纪律）。"""
    from ohscheck.loaders import load_path
    from ohscheck.rules.schema import SYNTHETIC_MARKER

    obj = load_path(os.path.join(bench_dir(), "ruleset-2025.json"))
    assert obj["synthetic"] is True
    assert obj["basis"]["doc_code"].startswith(SYNTHETIC_MARKER)
    assert obj["basis"]["issuer"] == ""


def test_production_rulesets_are_not_synthetic():
    """生产规则包不是合成夹具（synthetic=false）。"""
    from ohscheck.loaders import load_path

    obj = load_path(os.path.join(data_dir(), "rules", "ruleset-2025.json"))
    assert obj.get("synthetic") is False
    assert obj["basis"]["doc_code"] == "GBZ 188—2025"


def test_production_rulesets_are_all_pending_at_m0():
    """M0 初态：生产规则包全部条目 pending（未核对不得进入核查路径）。"""
    from ohscheck.loaders import load_path

    for name in ("ruleset-2014.json", "ruleset-2025.json"):
        obj = load_path(os.path.join(data_dir(), "rules", name))
        for factor in obj["factors"]:
            assert factor["status"] == "pending", (name, factor["factor_code"])
            assert factor["period"]["value"] is None
