"""M5：GUI 分层守门 + 三方对账行为等价 + 惰性导入回归。

对应 DoD：M5-2/M5-3/M5-4/M5-10（plan/05 §四 M5）。

三条 AST 守门（plan/04 §十，FR-G2）——表现层只做展示与转发：
    ① 不 import 规则层：``gui/`` 下除 ``gui/service.py`` 外**任何模块**
      不得 import ``ohscheck`` 的引擎/规则/报告/基准子包；
    ② 无 ``BinOp`` 算术：``gui/pages/*.py`` 编译树里不得出现任何二元运算；
    ③ 无政策数值字面量：用 ``tools/check_literals`` 的同一 token 实算口径
      扫 ``gui/pages/*.py``（周期月数/切口日/年度等不得抄进界面层）。

三方对账（FR-G3）：CLI stdout == pipeline 直调 == 报告章节——**行为等价**，
不是"都调了同一个函数"的字面声明。
"""

from __future__ import annotations

import ast
import io
import json
import os
import sys

import pytest

import helpers
from helpers import make_factor, make_record, make_temp_data_dir, write_json

from ohscheck.cli import main

_REPO_ROOT = helpers.repo_root()
_GUI_DIR = os.path.join(_REPO_ROOT, "src", "ohscheck", "gui")


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


def _parse(path):
    with open(path, "r", encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _gui_py_files(subdir=None):
    root = os.path.join(_GUI_DIR, subdir) if subdir else _GUI_DIR
    out = []
    for cur, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(".py"):
                out.append(os.path.join(cur, name))
    return sorted(out)


# ---------------- M5-3 守门①：表现层不 import 规则层 ----------------


def test_gui_layers_only_service_imports_engine():
    """gui/ 下除 service.py 外，不得 import ohscheck 引擎/规则/报告/基准子包。"""
    bad = []
    for path in _gui_py_files():
        if os.path.normpath(path).endswith(
            os.path.normpath(os.path.join("gui", "service.py"))
        ):
            continue  # 服务层是唯一允许 import 引擎的模块（plan/04 §十）
        tree = _parse(path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if not name.startswith("ohscheck"):
                    continue
                if name.startswith("ohscheck.gui"):
                    continue
                bad.append("%s:%d imports %s" % (path, node.lineno, name))
    assert not bad, "表现层/主窗口混入引擎 import：\n" + "\n".join(bad)


def test_gui_service_imports_pipeline_only():
    """service.py 的引擎 import 只准落在 ohscheck.engine.pipeline（唯一编排事实源）。"""
    path = os.path.join(_GUI_DIR, "service.py")
    tree = _parse(path)
    bad = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            if name.startswith("ohscheck") and not name.startswith("ohscheck.gui"):
                if name != "ohscheck.engine.pipeline" and not name.startswith(
                    "ohscheck.errors"
                ):
                    # errors 是异常翻译的契约面；paths 只准 is_frozen 一类判定
                    if name != "ohscheck.paths" or not os.path.normpath(path).endswith(
                        "service.py"
                    ):
                        bad.append("%s:%d imports %s" % (path, node.lineno, name))
    assert not bad, "service.py 绕开 pipeline 取数：\n" + "\n".join(bad)


# ---------------- M5-3 守门②：表现层无 BinOp 算术 ----------------


def test_gui_pages_have_no_binop_arithmetic():
    """gui/pages/*.py 编译树不得出现任何 BinOp（界面层不做计算）。"""
    bad = []
    for path in _gui_py_files("pages"):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                bad.append("%s:%d BinOp(%s)" % (path, node.lineno, type(node.op).__name__))
    assert not bad, "页签层出现算术：\n" + "\n".join(bad)


# ---------------- M5-3 守门③：表现层无政策数值字面量 ----------------


def test_gui_pages_carry_no_policy_literals():
    """用 check_literals 的同一 token 实算口径扫 gui/pages（字面量门禁 M5 起含 GUI）。"""
    sys.path.insert(0, os.path.join(_REPO_ROOT, "tools"))
    try:
        import check_literals

        tokens = check_literals.collect_tokens()
        patterns = check_literals._build_patterns(tokens)
        page_files = _gui_py_files("pages")
        hits = check_literals.scan_files(page_files, patterns)
        assert not hits, "政策数值字面量抄进界面层：\n" + "\n".join(
            "%s:%d [%s]" % (h["file"], h["line"], h["token"]) for h in hits
        )
    finally:
        sys.path.pop(0)


# ---------------- M5-2 GUI 六页签（结构断言 + offscreen 冒烟）----------------

EXPECTED_TABS = ("自检", "岗位应检", "档案核查", "批量扫描", "版本对照", "报告导出")


def test_gui_main_window_declares_six_tabs():
    """PAGE_BUILDERS 六页签、顺序与 plan/05 M5-2 一致。"""
    pytest.importorskip("PySide6")
    from ohscheck.gui.main_window import PAGE_BUILDERS

    titles = tuple(title for title, _builder in PAGE_BUILDERS)
    assert titles == EXPECTED_TABS


def test_gui_build_app_offscreen_smoke(monkeypatch):
    """offscreen 冒烟：build_app 构造主窗口 + 六页签实例化不崩。"""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from ohscheck.gui.main_window import build_app

    app, window = build_app(None)
    tabs = window.centralWidget()
    assert tabs.count() == 6
    for index, title in enumerate(EXPECTED_TABS):
        assert tabs.tabText(index) == title


def test_gui_cli_smoke_offscreen_exit_0(monkeypatch):
    """CLI `gui` 冒烟：offscreen + 自动退出通道 → exit 0。"""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("OHSCHECK_GUI_SMOKE", "1")
    code, _out, err = _run(["gui"])
    assert code == 0, err


# ---------------- M5-10 惰性导入 try 包住整段 + exit 3 回归 ----------------


def test_gui_import_error_during_call_still_exits_3(monkeypatch):
    """D-38 回归：import 成功但**调用**阶段才缺依赖（如 Qt 插件加载失败）
    → 同一 try 整段兜住 → 退出码 3，不崩。
    """
    import ohscheck.gui.main_window as mw

    def boom(_data_dir=None):
        raise ImportError("libEGL.so: cannot open shared object (stubbed)")

    monkeypatch.setattr(mw, "main", boom)
    code, _out, err = _run(["gui"])
    assert code == 3, err
    assert "PySide6" in err


def test_gui_missing_pyside6_exits_3_without_pyside6(monkeypatch):
    """PySide6 缺失（打桩 __import__）→ 退出码 3（本机装了 extra 也必测）。"""
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


# ---------------- M5-4 三方对账：CLI stdout == pipeline 直调 == 报告章节 ----------------


@pytest.fixture()
def real_env():
    """真实规则包（苯，第 5 章已核对因素）做三方对账。"""
    return {"data_dir": None}


_BENZENE_POSITION = {
    "position_id": "POS-RECON-1",
    "exam_date": "2026-09-15",
    "factors": [{"factor_code": "GBZ188-5.19"}],
}


def _pipeline_plan(data_dir):
    from ohscheck.engine.pipeline import build_context, build_position, compute_plan

    profile = build_position(_BENZENE_POSITION)
    return compute_plan(profile, build_context(data_dir)).as_dict()


def _report_texts(tmp_path, position_obj=None, record_path=None):
    """跑 report 导出，返回 markdown 文本。"""
    from ohscheck.engine.pipeline import build_context, report_from_inputs

    out = os.path.join(str(tmp_path), "recon-out")
    position_path = None
    if position_obj is not None:
        position_path = os.path.join(str(tmp_path), "pos-recon.json")
        write_json(position_path, position_obj)
    report_from_inputs(
        out_dir=out,
        context=build_context(None),
        generated_at="2026-10-14T00:00:00",
        position_path=position_path,
        record_path=record_path,
    )
    with open(os.path.join(out, "report.md"), "r", encoding="utf-8") as fh:
        return fh.read()


def test_three_way_agreement_plan(real_env, tmp_path, monkeypatch):
    """plan 通路三方对账：CLI stdout == pipeline 直调（逐字段）== 报告章节内容。"""
    monkeypatch.setenv("OHSCHECK_TMP", str(tmp_path))
    pos_path = os.path.join(str(tmp_path), "pos.json")
    write_json(pos_path, _BENZENE_POSITION)

    code, out, err = _run(["plan", pos_path, "--json"])
    assert code == 0, err
    cli_payload = json.loads(out)

    pipeline_payload = _pipeline_plan(None)
    assert cli_payload == pipeline_payload  # 逐字段一致（同一输入）

    # 两次调用逐字段一致（确定性）
    code2, out2, _err2 = _run(["plan", pos_path, "--json"])
    assert code2 == 0
    assert json.loads(out2) == cli_payload

    # 第三方：报告章节承载同一结论（应检项目与因素名）
    markdown = _report_texts(tmp_path, position_obj=_BENZENE_POSITION)
    plan = cli_payload["factors"][0]
    for item in plan["exams"]["periodic"]["required_items"]:
        assert item in markdown, "报告缺应检项目：%s" % item
    assert plan["factor_name"] in markdown


def test_three_way_agreement_check(real_env, tmp_path, monkeypatch):
    """check 通路三方对账：CLI stdout == pipeline 直调 == 报告章节。"""
    monkeypatch.setenv("OHSCHECK_TMP", str(tmp_path))
    rec = make_record(
        record_id="RECON-REC-1",
        factor_code="GBZ188-5.19",
        exam_date="2026-09-15",
        exam_type="periodic",
        items=("血常规", "尿常规", "肝功能", "心电图", "肝脾B超"),
        last_exam_date="2025-10-01",
    )
    rec_path = os.path.join(str(tmp_path), "rec.json")
    write_json(rec_path, rec)

    code, out, err = _run(["check", rec_path, "--json"])
    assert code == 0, err
    cli_payload = json.loads(out)

    from ohscheck.engine.pipeline import build_context, build_record, compute_coverage
    from ohscheck.loaders import load_path

    pipeline_payload = compute_coverage(
        build_record(load_path(rec_path)), build_context(None)
    ).as_dict()
    assert cli_payload == pipeline_payload

    markdown = _report_texts(tmp_path, record_path=rec_path)
    assert cli_payload["verdict"] in markdown or "覆盖度" in markdown


def test_gui_service_agrees_with_cli_stdout(real_env, tmp_path, monkeypatch):
    """GUI 服务层（唯一引擎入口）与 CLI stdout 行为等价：plan/check/compare 逐字段一致。"""
    monkeypatch.setenv("OHSCHECK_TMP", str(tmp_path))
    pos_path = os.path.join(str(tmp_path), "pos.json")
    write_json(pos_path, _BENZENE_POSITION)

    from ohscheck.gui.service import Service

    service = Service(None)

    code, out, err = _run(["plan", pos_path, "--json"])
    assert code == 0, err
    assert service.plan(_BENZENE_POSITION) == json.loads(out)

    rec = make_record(
        record_id="RECON-REC-2",
        factor_code="GBZ188-5.19",
        exam_date="2026-09-15",
        exam_type="periodic",
        items=("血常规", "尿常规"),
        last_exam_date="2025-10-01",
    )
    rec_path = os.path.join(str(tmp_path), "rec2.json")
    write_json(rec_path, rec)
    code, out, err = _run(["check", rec_path, "--json"])
    assert code in (0, 1), err
    assert service.check(rec) == json.loads(out)

    code, out, err = _run(["compare", "--json"])
    assert code == 0, err
    ids = service.ruleset_ids()
    assert service.compare(ids[0], ids[-1]) == json.loads(out)


def test_gui_service_selfcheck_agrees_with_cli():
    """GUI 服务层 selfcheck 与 CLI selfcheck 负载一致。"""
    from ohscheck.gui.service import Service

    code_cli, out, err = _run(["selfcheck", "--json"])
    assert code_cli == 0, err
    payload, code = Service(None).selfcheck()
    assert code == 0
    assert payload == json.loads(out)


# ---------------- M5-7 spec 生成器守门（datas 白名单单一事实源） ----------------


def test_spec_matches_generated_from_whitelist():
    """tools/packaging.spec 必须与 gen_spec.py 再生成逐字节一致（禁手改，gen_* 惯例）。"""
    sys.path.insert(0, os.path.join(_REPO_ROOT, "tools"))
    try:
        import gen_spec

        ok, message = gen_spec.check()
        assert ok, message
        # datas 行必须来自 ohscheck.packaging.DATA_WHITELIST（单一事实源）
        from ohscheck.packaging import DATA_WHITELIST

        text = gen_spec.spec_text()
        for src_rel, dest_rel in DATA_WHITELIST:
            assert src_rel in text and dest_rel in text
        # 禁区段不得出现在 spec
        for forbidden in ("knowledge/raw",):
            assert forbidden not in text
    finally:
        sys.path.pop(0)


def test_packaging_whitelist_covers_required_dirs_and_blocks_raw():
    """白名单须含 rules/benchmark/truth；禁区段声明须拦住 knowledge/raw。"""
    from ohscheck.packaging import DATA_WHITELIST, FORBIDDEN_DATA_PREFIXES, build_datas

    sources = [src for src, _dest in DATA_WHITELIST]
    for required in ("data/rules", "data/benchmark", "data/truth"):
        assert required in sources, "白名单缺 %s" % required
    assert "data/knowledge/raw" in FORBIDDEN_DATA_PREFIXES
    # build_datas 产出的 src 不得落在禁区段内
    for src_abs, _dest in build_datas():
        assert "knowledge" not in src_abs.replace("\\", "/").split("data/")[-1] or (
            "raw" not in src_abs.replace("\\", "/")
        )
