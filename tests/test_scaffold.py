"""骨架守门：零字面量门禁的阳性对照、打包白名单、CI 取全量历史、结构纪律。

对应 DoD：M0-10（门禁带 selftest）、M0-14（CI fetch-depth 守门）。
"""

from __future__ import annotations

import io
import os
import re
import sys

import pytest

from helpers import repo_root

from ohscheck import packaging
from ohscheck.packaging import FORBIDDEN_DATA_PREFIXES, build_datas

import json


# ---------------- 零字面量门禁（决策 D-27）----------------


def _run_literals(*args):
    """以子进程语义在进程内跑门禁（避免 import 副作用）。"""
    import importlib.util

    root = repo_root()
    path = os.path.join(root, "tools", "check_literals.py")
    spec = importlib.util.spec_from_file_location("check_literals_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_literals_selftest_reports_positive_control(capsys):
    """门禁的阳性对照必须能报出（否则"0 命中"是空转，决策 D-27）。"""
    module = _run_literals()
    code = module.main(["--selftest"])
    captured = capsys.readouterr()
    assert code == 0
    assert "LITERALS_SELFTEST_OK" in captured.out


def test_literals_selftest_detects_docstring_and_literal():
    """阳性对照覆盖三种藏点：赋值、docstring、字符串字面量。"""
    module = _run_literals()
    import tempfile

    tmp = tempfile.mkdtemp(prefix="ohscheck-lit-test-")
    sample = os.path.join(tmp, "m.py")
    token = 4242
    with open(sample, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("X = %d\n" % token)
        fh.write("def f():\n    '''doc %d'''\n    return 'lit %d'\n" % (token, token))
    hits = module.scan_files([sample], [(r"\b%d\b" % token, "t:%d" % token)])
    assert len(hits) >= 3


def test_literals_gate_is_nonvacuous_after_m1_ingest(capsys):
    """M1 数据入库后，token 集**必须非空**（门禁真正具备数值拦截力）。

    M0 期规则包全 pending/null ⇒ token 集为空、门禁空转（当时已如实留档）。
    M1 起第 5–7 章周期月数已落库 ⇒ 门禁不再空转——本测试守住这个转折。
    """
    module = _run_literals()
    code = module.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["token_count"] > 0, "M1 后 token 集不应再为空"
    assert payload["vacuous"] is False
    assert code == 0  # 无命中即 0（源代码里不得出现规则包数值）


def test_literals_gate_scans_expected_surfaces():
    module = _run_literals()
    root = repo_root()
    files = module._iter_source_files(root)
    rels = [os.path.relpath(f, root).replace("\\", "/") for f in files]
    assert any(r.startswith("src/ohscheck/engine/") for r in rels)
    assert any(r.startswith("src/ohscheck/rules/") for r in rels)
    assert any(r.startswith("src/ohscheck/report/") for r in rels)
    assert "src/ohscheck/cli.py" in rels


# ---------------- 打包白名单（决策 D-15，骨架期先立）----------------


def test_packaging_module_is_inside_package_not_top_level():
    """packaging 必须放包内，不占仓库顶层名（否则遮蔽 PyPI packaging）。"""
    root = repo_root()
    assert os.path.isfile(os.path.join(root, "src", "ohscheck", "packaging.py"))
    assert not os.path.isfile(os.path.join(root, "packaging.py"))


def test_build_datas_excludes_forbidden_prefixes(monkeypatch, tmp_path):
    """白名单不得含禁区段（版权原文快照一律不入包）。"""
    monkeypatch.setattr(
        packaging, "DATA_WHITELIST", (("data/knowledge/raw", "data/knowledge/raw"),)
    )
    with pytest.raises(RuntimeError) as e:
        build_datas()
    assert "禁区" in str(e.value)


def test_build_datas_returns_whitelisted_rules_dir():
    datas = build_datas()
    dests = [dest for _src, dest in datas]
    assert "data/rules" in dests
    for src, _dest in datas:
        assert os.path.isdir(src)


def test_forbidden_prefixes_cover_knowledge_raw_and_private():
    joined = " ".join(FORBIDDEN_DATA_PREFIXES)
    assert "knowledge/raw" in joined
    assert "_private" in joined


# ---------------- CI：fetch-depth 守门（决策 D-40）----------------


def _ci_config():
    import yaml  # noqa: F401  (pytest 环境未必有；缺失则跳过)
    root = repo_root()
    path = os.path.join(root, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _parse_checkout_fetch_depths(text):
    """解析 workflow 文本，返回每个 checkout step 的 fetch-depth 字符串列表。"""
    depths = []
    # 逐行扫描：遇到 uses: actions/checkout 后，在其后的缩进块里找 fetch-depth
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if "uses: actions/checkout" in line:
            base_indent = len(line) - len(line.lstrip())
            depth = None
            for follow in lines[idx + 1 : idx + 12]:
                stripped = follow.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                indent = len(follow) - len(follow.lstrip())
                if indent < base_indent:
                    break
                if stripped.startswith("- ") and indent <= base_indent:
                    break
                if "fetch-depth" in stripped:
                    depth = stripped.split(":", 1)[1].strip()
                    break
            depths.append(depth)
    return depths


def test_ci_workflow_exists():
    root = repo_root()
    assert os.path.isfile(os.path.join(root, ".github", "workflows", "ci.yml"))


def test_every_checkout_uses_fetch_depth_0():
    """历史扫描类守门测试依赖全量历史；浅克隆会让扫描静默空转（决策 D-40）。"""
    text = _ci_config()
    depths = _parse_checkout_fetch_depths(text)
    assert depths, "CI 未发现 actions/checkout 步骤"
    for depth in depths:
        assert depth == "0", "checkout 必须配 fetch-depth: 0，实际 %r" % depth


def test_ci_matrix_covers_four_combinations():
    """4 矩阵：{ubuntu, windows} × {3.8, 3.12}（NFR-6）。"""
    text = _ci_config()
    assert "ubuntu-latest" in text
    assert "windows-latest" in text
    assert "'3.8'" in text or '"3.8"' in text
    assert "'3.12'" in text or '"3.12"' in text


def test_ci_runs_tests_bench_and_guards():
    text = _ci_config()
    assert "pytest" in text
    assert "bench" in text
    assert "check_literals" in text
    assert "gen_rulesets" in text


# ---------------- 结构纪律 ----------------


def test_core_has_no_third_party_imports():
    """核心层零第三方依赖（NFR-3 / 决策 D-07）：只许 stdlib。

    用 AST 静态扫描，比运行时 import 更可靠。
    3.8 没有 sys.stdlib_module_names（3.10+）→ 回落到显式 stdlib 白名单，
    **不允许"环境缺能力就静默跳过"**（否则守门在某条通道上假绿）。
    """
    import ast

    if hasattr(sys, "stdlib_module_names"):
        allowed = set(sys.stdlib_module_names)
    else:
        # 3.8 显式白名单：本项目实际用到的 stdlib 模块 + 常见同族
        allowed = {
            "argparse", "ast", "calendar", "collections", "contextlib", "copy",
            "csv", "dataclasses", "datetime", "decimal", "enum", "errno", "functools",
            "hashlib", "io", "itertools", "json", "logging", "math", "os", "pathlib",
            "re", "shutil", "stat", "string", "struct", "subprocess", "sys",
            "tempfile", "textwrap", "time", "types", "typing", "unicodedata",
            "unittest", "warnings", "xml", "zipfile", "__future__",
        }

    offenders = []
    src_root = os.path.join(repo_root(), "src", "ohscheck")
    for cur, dirs, files in os.walk(src_root):
        # gui/ 允许在函数体内惰性 import PySide6（由 AST 守门另行约束）
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(cur, name)
            rel = os.path.relpath(path, repo_root()).replace("\\", "/")
            is_gui = rel.startswith("src/ohscheck/gui/")
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top == "ohscheck" or top in allowed:
                            continue
                        if is_gui and top == "PySide6":
                            continue
                        offenders.append((path, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # 相对导入（from . import x）→ 包内，跳过
                        continue
                    top = (node.module or "").split(".")[0]
                    if not top or top == "ohscheck" or top in allowed:
                        continue
                    if is_gui and top == "PySide6":
                        continue
                    offenders.append((path, node.module))
    assert not offenders, "核心层出现第三方依赖：%s" % offenders


def test_core_has_no_network_imports():
    """零外联（NFR-1）：核心层不得 import 任何网络模块。"""
    import ast

    banned = {"requests", "urllib", "http", "socket", "ftplib", "smtplib", "telnetlib"}
    root = repo_root()
    offenders = []
    src_root = os.path.join(root, "src", "ohscheck")
    for cur, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(cur, name)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in banned:
                            offenders.append((path, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    if (node.module or "").split(".")[0] in banned:
                        offenders.append((path, node.module))
    assert not offenders, "出现网络模块 import：%s" % offenders


def test_decision_records_and_plan_docs_present():
    """plan/00–06 齐全（M0-1）。"""
    root = repo_root()
    for name in (
        "00-README总览.md",
        "01-题目详细定义.md",
        "02-需求解读.md",
        "03-架构与技术选型.md",
        "04-模块详设.md",
        "05-数据计划与里程碑.md",
        "06-决策记录.md",
    ):
        assert os.path.isfile(os.path.join(root, "plan", name)), name


def test_gitattributes_enforces_lf():
    root = repo_root()
    with open(os.path.join(root, ".gitattributes"), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "eol=lf" in text


def test_tools_scripts_have_utf8_guard():
    """所有会打印的工具入口都要有编码守卫（决策 D-39）。"""
    root = repo_root()
    tools_dir = os.path.join(root, "tools")
    for name in sorted(os.listdir(tools_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(tools_dir, name), "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "_ensure_utf8_stdio" in text, "%s 缺少编码守卫" % name


def test_selftest_writes_result_file(tmp_path):
    """冻结态自检结论写文件回传（FR-G5）；非冻结态不报 FAIL 于"落在 exe 内"。"""
    from ohscheck._selftest import run_selftest

    out = tmp_path / "selftest.json"
    code = run_selftest(str(out))
    assert out.is_file()
    payload = json.loads(out.read_bytes().decode("utf-8"))
    assert payload["frozen"] is False
    assert payload["data_dir_inside_exe"] is None  # 非冻结态：不判 FAIL，决策 D-37
    assert payload["engine_ok"] is True
    assert payload["bench_ok"] is True
    assert code == 0
