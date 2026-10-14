"""GUI 服务层（FR-G3 / plan/04 §十）——**GUI 唯一允许 import 引擎的模块**。

职责：把 engine/pipeline 的公开函数组适配成"输入可序列化、输出可渲染"的
服务接口。所有判定与 IO 都在编排层；本模块不做任何计算，只做取数转发与
异常翻译（引擎异常 → (ok, payload) 元组，供页签渲染错误）。

表现层（gui/pages/*）只准 import 本模块，不准 import ohscheck 其他子模块
（AST 守门测试锁死，M5-3）。
"""

from __future__ import annotations

from ..errors import OhsCheckError

__all__ = [
    "GUIError",
    "Service",
    "is_frozen",
]


class GUIError(Exception):
    """服务层转译后的业务失败（携带用户可读消息）。"""

    def __init__(self, message):
        super(GUIError, self).__init__(message)
        self.message = message


def _translate(func, *args, **kwargs):
    """引擎调用统一出口：OhsCheckError → GUIError，其余原样抛出。"""
    try:
        return func(*args, **kwargs)
    except OhsCheckError as exc:
        raise GUIError(exc.message)


class Service:
    """无状态服务对象：每个页签持有一个引用，方法即一次引擎调用。"""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir

    # ---- 编排上下文 ----

    def _context(self):
        from ..engine.pipeline import build_context

        return build_context(self.data_dir)

    # ---- 页签 1：自检 ----

    def selfcheck(self):
        """自检负载（规则库计数 + 参数来源 + 数据定位）→ (dict, exit_code)。"""
        from ..engine.pipeline import selfcheck_payload

        return _translate(selfcheck_payload, self.data_dir)

    # ---- 页签 2：岗位应检 ----

    def plan(self, profile_obj):
        """岗位应检清单推导：裸字典 → PlanResult 字典。"""
        from ..engine.pipeline import build_position, compute_plan

        profile = build_position(profile_obj)
        result = compute_plan(profile, self._context())
        return result.as_dict()

    # ---- 页签 3：档案核查 ----

    def check(self, record_obj):
        """单件覆盖度核查：裸字典 → CoverageResult 字典。"""
        from ..engine.pipeline import build_record, compute_coverage

        record = build_record(record_obj)
        result = compute_coverage(record, self._context())
        return result.as_dict()

    # ---- 页签 4：批量扫描 ----

    def scan(self, directory, baseline=None):
        """批量扫描（可选跨轮对账）→ ScanResult 字典（含 baseline/reconcile）。"""
        from ..engine.pipeline import build_context, scan_with_reconcile

        result, baseline_result, reconcile = scan_with_reconcile(
            directory, build_context(self.data_dir), baseline
        )
        payload = result.as_dict()
        if baseline_result is not None:
            payload["baseline"] = baseline_result.as_dict()
        if reconcile is not None:
            payload["reconcile"] = reconcile.as_dict()
        return payload

    # ---- 页签 5：版本对照 ----

    def ruleset_ids(self):
        """manifest 里的 ruleset_id 列表（对照页的下拉选项）。"""
        from ..engine.pipeline import build_context

        return list(build_context(self.data_dir).manifest.ruleset_ids())

    def compare(self, ruleset_id_a, ruleset_id_b):
        """双版本差异对照 → DiffReport 字典。"""
        from ..engine.pipeline import build_context, compare

        return compare(ruleset_id_a, ruleset_id_b, build_context(self.data_dir)).as_dict()

    # ---- 页签 6：报告导出 ----

    def export_report(self, out_dir, generated_at, position_path=None,
                      record_path=None, directory=None, baseline=None):
        """报告导出全链路（溯源断言 + 三件套落盘）→ 路径字典。"""
        from ..engine.pipeline import build_context, report_from_inputs

        return report_from_inputs(
            out_dir=out_dir,
            context=build_context(self.data_dir),
            generated_at=generated_at,
            position_path=position_path,
            record_path=record_path,
            directory=directory,
            baseline=baseline,
        )


def is_frozen():
    """冻结态查询（自检页展示用；转发 paths 判定）。"""
    from .. import paths

    return paths.is_frozen()
