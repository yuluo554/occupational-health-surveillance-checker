"""桌面界面（FR-G2/G3，M5）。

分层（plan/04 §十）：
    编排层  engine/pipeline.py 公开函数组 —— CLI 与 GUI 唯一取数入口
    服务层  ohscheck.gui.service —— GUI 唯一允许 import 引擎的模块
    表现层  ohscheck.gui.pages.* —— 只渲染；AST 三条守门（M5-3）
"""
