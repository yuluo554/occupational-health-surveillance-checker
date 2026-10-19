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
    # PyYAML 在 dev extras 里（M6-2 干净环境实测 L-1：缺它守门测试是红而非跳过，必须显式声明）
    import yaml  # noqa: F401
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


def test_ci_matrix_covers_supported_python_and_os():
    """2 矩阵：{ubuntu, windows} × {3.12}（迭代 D-3：3.8 已 EOL，不再进矩阵）。"""
    text = _ci_config()
    assert "ubuntu-latest" in text
    assert "windows-latest" in text
    assert "'3.12'" in text or '"3.12"' in text
    assert "'3.8'" not in text and '"3.8"' not in text


def test_runtime_floor_is_consistent_across_config_and_docs():
    """pyproject / CI / README / 技术报告 的运行时口径必须一致（迭代 D-3）。"""
    root = repo_root()
    pyproject = open(os.path.join(root, "pyproject.toml"), encoding="utf-8").read()
    assert 'requires-python = ">=3.12"' in pyproject
    assert 'gui = ["PySide6>=6.12,<7"]' in pyproject
    assert 'build = ["PyInstaller>=6.0,<7"]' in pyproject
    assert '"Programming Language :: Python :: 3.8"' not in pyproject
    readme = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert "要求 Python 3.12+" in readme
    # 旧的 3.8 口径（下限声明 / 双通道 / 4 矩阵）不得残留；历史事实性提及（如"3.8 已 EOL"）允许
    for stale in ("Python 3.8+", "要求 Python 3.8", "3.8 与 3.12 双通道", "4 矩阵", "{3.8, 3.12}"):
        assert stale not in readme, "README 仍残留旧口径：%s" % stale
    assert "2 矩阵" in readme
    report = open(os.path.join(root, "docs", "技术报告.md"), encoding="utf-8").read()
    for stale in ("Python 3.8+", "3.8.8 与 3.12 双通道"):
        assert stale not in report, "技术报告仍残留旧口径：%s" % stale


def test_ci_runs_tests_bench_and_guards():
    text = _ci_config()
    assert "pytest" in text
    assert "bench" in text
    assert "check_literals" in text
    assert "gen_rulesets" in text


# ---------------- 脱敏门禁：plan/ 不豁免 + CI 常驻（迭代 D-1）----------------


def _audit_module():
    import importlib.util

    root = repo_root()
    path = os.path.join(root, "tools", "audit_sensitive.py")
    spec = importlib.util.spec_from_file_location("audit_sensitive_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_has_no_whole_dir_exemption():
    """plan/ 整目录豁免必须不存在（RELEASE-M6 §六 口径与代码一致）。"""
    root = repo_root()
    with open(os.path.join(root, "tools", "audit_sensitive.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "PLAN_EXCLUDE" not in text
    assert "startswith(PLAN_EXCLUDE" not in text


def test_audit_selftest_covers_plan_path(capsys):
    """selftest 必须有 plan/ 阳性对照（否则"plan/ 已扫描"无法证伪）。"""
    module = _audit_module()
    patterns, needles, _provenance = module.collect_tokens(repo_root())
    code = module._selftest(patterns, needles)
    captured = capsys.readouterr()
    assert code == 0
    assert "AUDIT_SELFTEST_OK" in captured.out
    assert "plan/ 路径阳性对照报出" in captured.out


def test_audit_selftest_reports_plan_and_real_paths(capsys):
    """中性占位豁免必须是窄的：占位式路径放行、真实路径仍报出。"""
    module = _audit_module()
    patterns, needles, _provenance = module.collect_tokens(repo_root())
    module._selftest(patterns, needles)
    out = capsys.readouterr().out
    assert "中性占位豁免 0 命中且真实路径仍报出" in out


def test_audit_tree_scan_includes_plan_and_reads_every_file():
    """工作树扫描必须真的读到每个文件（非 ASCII 路径不得因引号转义静默漏读）。"""
    module = _audit_module()
    root = repo_root()
    files = module._tracked_files(root)
    assert files, "已跟踪文件清单为空"
    assert not [f for f in files if f.startswith('"')], "git ls-files 路径仍被引号转义"
    assert any(f.replace("\\", "/").startswith("plan/") for f in files)
    patterns, _needles, _provenance = module.collect_tokens(root)
    result = module.step1_tree(root, patterns)
    assert result["unreadable"] == []
    assert result["scanned"] == len(files)


def test_ci_runs_sensitive_audit_gate():
    """脱敏门禁必须常驻 CI（selftest + 全跑），否则只在人工跑。"""
    text = _ci_config()
    assert "audit_sensitive.py --selftest" in text
    assert text.count("audit_sensitive.py") >= 2


# ---------------- README 可运行示例接线（迭代 D-2）----------------


def _run_cli(argv):
    import io as _io

    from ohscheck.cli import main as cli_main

    out, err = _io.StringIO(), _io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = cli_main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


def test_examples_position_sample_runs_plan_exit_0():
    """仓内示例岗位画像必须能被 `plan` 直接跑通（README 第 2 条命令）。"""
    root = repo_root()
    sample = os.path.join(root, "examples", "position-sample.json")
    assert os.path.isfile(sample), "examples/position-sample.json 缺失"
    payload = json.loads(open(sample, encoding="utf-8").read())
    for key in ("position_id", "exam_date", "factors"):
        assert key in payload, "示例岗位画像缺字段 %r" % key
    code, out, err = _run_cli(["plan", sample])
    assert code == 0, "plan 退出码 %d；stderr=%s" % (code, err[:400])
    assert "SYN-POS-benzene" in out
    assert "GBZ188-5.19" in out


def test_readme_example_paths_exist():
    """README 里出现的每个 examples/... 路径都必须存在（防文档漂移）。"""
    root = repo_root()
    text = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    paths = sorted(set(re.findall(r"examples/[A-Za-z0-9._/-]+", text)))
    assert paths, "README 未引用任何 examples/ 路径"
    for rel in paths:
        assert os.path.isfile(os.path.join(root, rel.replace("/", os.sep))), rel


def test_readme_command_paths_exist():
    """README 命令块里引用的仓内数据路径必须存在（真值库 / 示例目录）。"""
    root = repo_root()
    text = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    for rel in ("data/truth/records", "examples/position-sample.json"):
        assert rel in text, "README 命令块未引用 %s" % rel
        assert os.path.exists(os.path.join(root, rel.replace("/", os.sep))), rel


# ---------------- 结构纪律 ----------------


def test_core_has_no_third_party_imports():
    """核心层零第三方依赖（NFR-3 / 决策 D-07）：只许 stdlib。

    用 AST 静态扫描，比运行时 import 更可靠。
    floor 已是 3.12（迭代 D-3）⇒ `sys.stdlib_module_names` 必然存在；
    **不允许"环境缺能力就静默跳过"**（否则守门会在某条通道上假绿）。
    """
    import ast

    if not hasattr(sys, "stdlib_module_names"):
        pytest.fail("解释器缺 sys.stdlib_module_names——floor 应为 >=3.12（迭代 D-3）")
    allowed = set(sys.stdlib_module_names)

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
