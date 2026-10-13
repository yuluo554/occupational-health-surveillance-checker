"""内置评测基准（FR-E1–E6）。

纪律：
  * 零 API 依赖、零第三方依赖，离线可跑；
  * **验收门槛随 manifest 下发**（数据非代码，决策 D-24），缺失即退出码 2；
  * 每套件配**可证伪探活**（注入缺陷 → 必须报未达标）；
  * `--only` 传未知名 → 退出码 2（决策 D-25）；
  * 样本驱动 + 规则驱动两层（plan/04 §9.2）。
"""

from __future__ import annotations

from .runner import SUITES, run_benchmarks

__all__ = ["SUITES", "run_benchmarks"]
