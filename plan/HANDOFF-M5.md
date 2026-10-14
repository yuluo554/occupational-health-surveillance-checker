# HANDOFF-M5：桌面交付与打包（下一棒续接快照）

> **状态**：M4 已完结（2026-10-14），本文件是 M5 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M5.md`，避免入库本机盘符路径）

---

## 一、当前进度（M4 完结实态）

**交付物**：**内置基准收口**——四套件（matrix/coverage/compare/false_positive）+ `--only` 白名单 + **每套件可证伪探活**（`tests/test_m4.py` 15 项：篡改期望应检清单 / 打桩 `judge_period` / 真值翻转 / 差异 kind 破坏 / 规则集删因素 / 弄脏干净档案 / 时长上限压 0，全部必红）+ **运行时长门槛真执行**（`max_runtime_seconds` 从死配置变被执行，超时 exit 1）+ **"未启用"套件不冒充通过**（空分母 → `not_enabled` + 写明"该类用例未生成" + exit 1）+ 门槛值统一 `parse_decimal` 归一 + 指标实测值入 README。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **212 项**（M3 基线 197 + 新增 `tests/test_m4.py` 15 项），Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 1.0000（5+规则驱动 7）、coverage 1.0000（13）、compare 1.0000（3）、false_positive 误报 0（7 件）、运行时长 0.005 秒（上限 5.0）；实测值已入 README"M4 期基准指标实测"表 |
| 官方快照 | `data/knowledge/raw/GBZ188-2025.pdf`（1,553,783 字节，sha256 `5823eea7…`）+ `.layout.txt`（**75,555 汉字**零丢失） |
| 规则包 | `data/rules/`（3 文件）：**2025 版 97 因素**（第 5–7 章 82 因素明细 verified，2520 条 verified）/ **2014 版 81 因素**差异骨架（明细全 pending）；`--check` 再生成逐字节一致 |
| 依据索引 | `data/knowledge/clauses.json`（97 节 + 前言差异 17 条 + 待核对项 4 条）；与规则包同一次 `--check` 守门 |
| 合成真值库 | `data/truth/`（**74 文件**：72 档案 + truth.json + manifest.json）；自研 splitmix64 seed 20261014；`--check` 位级一致；**72/72 与引擎对账 0 不一致** |
| CI | `.github/workflows/ci.yml`（4 矩阵 + `fetch-depth: 0` + `gen_synthetic.py --check`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M4 完成证据**：`plan/05-数据计划与里程碑.md` §四 M4 DoD 表（6/6 逐项证据 + 实测发现 J-1–J-2）。
**M4 决策**：`plan/06` D-74–D-75。

**关键结构事实（M1–M4 实测，务必先读）**：

- GBZ 188—2025 真实章节：**第 5 章化学（5.1–5.65，65 节）/ 第 6 章粉尘（6.1–6.9）/ 第 7 章物理（7.1–7.8）/ 第 8 章生物（8.1–8.5）/ 第 9 章特殊作业（9.1–9.10）**。
- 第 5–7 章（82 因素）**明细已核对**；第 8–9 章（15 因素）**仅因素身份已核对、明细 pending**。
- 周期：**38 因素单值**（12/24/36 月）；**22 因素分档 → `period.status=input_required`**（D-13/D-53/D-62）；**22 因素无在岗期间检查**（`kind=none` → `not_applicable`，D-62）；**15 因素 pending**（第 8–9 章）。
- **报告取数面**：§4/§5/§8 = `coverage_results + scan_result.items` 合并（D-67）；§6 统计两维（`by_factor` + `by_position`）+ `detail_sha256`（D-69）；§7 对账由 `--baseline` 驱动（D-70），`content_changed` 单列（D-20/D-70）。
- **基准层事实（M4 新）**：门槛**全部**走 `BenchEnv.threshold()`（`parse_decimal` 归一，缺键即 `MissingThresholdError` → exit 2，D-24）；`max_runtime_seconds` 已被执行（缺失 → 时长维度不判定，D-75）；空分母 → `not_enabled=true` + exit 1（D-74）；runner 在套件函数内**延迟 import** 引擎函数（探活打桩在运行期可达）。
- **失败件原因码全 8 个**（`errors.py`）：`read_error`/`bad_json`/`schema_invalid`/`unknown_factor`/`unknown_exam_type`/`container_too_large`/`gate_blocked`/`missing_input`。
- 真值件编号：**001–024 算例**，**025–072 批量件**（splitmix64 驱动 48 件）。

---

## 二、M5 待办（按序）

> M5 目标（`plan/05` §四）：**桌面交付与打包**——GUI 六页签 + PyInstaller onedir 双 exe + 三方对账行为等价 + 演示素材 + 技术报告。
> **注意**：M5 的多项前提**从未实测过**（HANDOFF-M4 §四明示）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收。逐项先 Spike 再固化。

### 2.1 M5-1 编排上收

| # | 任务 | 判据 |
|---|---|---|
| 1 | `engine/pipeline.py` 编排上收为公开函数组；CLI 行为不变 | 迁移前先跑双通道全绿作为**基线**；迁移后 212 项全绿 + CLI 端到端测试不改一字 |

### 2.2 M5-2 GUI 六页签

| # | 任务 | 判据 |
|---|---|---|
| 1 | PySide6 版本按老解释器上限 Spike 实测锁定（3.8 → 6.6.3.1 量级） | 实装实测记录进决策表（M5-5） |
| 2 | 六页签：自检/岗位应检/档案核查/批量扫描/版本对照/报告导出 | 分层纪律见 plan/04 §十：表现层只渲染，**AST 三条守门**（不 import 规则层 + 无 `BinOp` 算术 + 无政策数值字面量，M5-3）；GUI 唯一允许 import 引擎的是 `gui/service.py`；取数只走 pipeline（M5-1） |
| 3 | 惰性导入 `try` **包住从 import 到调用完成整段**（D-38 已有）；`__import__` 打桩回归 exit 3（M5-10） | 缺依赖 → 退出码 3，不崩 |

### 2.3 M5-3/M5-4 三方对账

- AST 三条守门锁进测试（M5-3）；
- **行为等价测试**：CLI stdout == pipeline 直调 == 报告章节（M5-4），**不是**断言"都调了同一个函数"的字面声明。

### 2.4 M5-6…M5-9 打包链

| # | 任务 | 判据 |
|---|---|---|
| 1 | PyInstaller **≥6**（打 GUI 硬下限；5.x 确定性崩在 PySide6 字节码扫描，D-14） | 构建实测记录 |
| 2 | onedir 双 exe；datas 白名单单一事实源 + 构建后三断言（M5-7） | rules/truth/samples 白名单入包；**不整仓塞 `data/`** |
| 3 | 冻结态 `--selftest <out.json>`：断言 `frozen=true` + **数据目录落在 dist 内** + 规则数 > 0（M5-8） | 真跑（此前从未跑过） |
| 4 | 中立目录（Temp + 剥离 PATH）双 exe 验收（M5-9） | exe 目录为 CWD |

### 2.5 M5-11/M5-12 演示素材与技术报告

- 演示素材程序化产出（PNG + GIF），**两次生成 sha256 逐个一致**（M5-11）；
- `docs/技术报告.md` 入仓（M5-12）；H-6 缓议项（是否另出 docx）此时裁决。

### 2.6 M5 收尾

- 回写 `plan/00` 状态表、`plan/05` M5 DoD 逐项证据、`plan/06` 决策记录（M5 新发现）；
- 写 `plan/HANDOFF-M6.md`（六段式）；
- 提交（正常开发流）。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全量口径速查见 `plan/HANDOFF-M4.md` §三（历史快照）或 `plan/06`。本节只列与 M5 直接相关的。

| 口径 | 内容 | 落点 |
|---|---|---|
| **GUI 分层三守门** | 表现层：不 import 规则层 + 无 `BinOp` 算术 + 无政策数值字面量；`gui/service.py` 是 GUI 唯一允许 import 引擎的模块 | plan/04 §十；M5-3 |
| **pipeline 是唯一编排事实源** | CLI 与 GUI 共用；表现层只准经它取数 | `engine/pipeline.py`；M5-1 |
| **行为等价 = 三方结论一致** | CLI stdout == pipeline 直调 == 报告章节；同一输入两次调用逐字段一致 | M5-4 |
| **PyInstaller ≥6 打 GUI** | 5.x 确定性崩；发布构建固定 3.12 通道（D-14） | M5-6 |
| **XLSX 自写最小 OOXML writer** | 否决 openpyxl（D-06）；XLSX 导出缺依赖时降级 CSV 不崩（00 预检③） | 报告层 |
| **门槛随 manifest 下发** | 基准门槛读 `manifest.benchmark_thresholds`，缺失即 exit 2，不回落代码默认值（D-24）；`max_runtime_seconds` 已被执行（D-75） | `benchmark/runner.py` |
| **"未启用"不冒充通过** | 基准空分母 → not_enabled + exit 1（D-74）；报告"未启用"章节显式写出（D-35/D-72） | 基准层 / 报告层 |
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |
| **品牌隔离** | 公开文档不提姊妹项目业务领域 | 00 决策记录 |

---

## 四、本机环境坑（**只写实测过的**；全量见 `plan/HANDOFF-M4.md` §四）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **heredoc 里的非 ASCII** | `py -3.8 - <<'PY'` 内联中文补丁偶发编码报错 | 长中文补丁走**临时 .py 文件**（仓库树外，如 `<workdir>/_m5_scratch.py`），首行 `# -*- coding: utf-8 -*-`，跑完即删 |
| **Git Bash `/tmp` 与 Windows Python 不通** | heredoc 里写 `/tmp/x` → FileNotFoundError | 临时目录用仓库树外 Windows 路径 |
| **`py -0p` 有两条通道** | 3.8.8 与 3.12 并存 | 双通道各跑一遍；**M5 打包固定 3.12（D-14）** |
| **json.dumps 不能直接序列化 Decimal** | 载入 `parse_float=Decimal` 后改数据写回会 TypeError | 测试用 `ohscheck.loaders.dumps_stable`；**注意它会把它数值小数写成 JSON 字符串**（M4 J-2 实测）——回写后再读入的数值门槛须归一（`BenchEnv.threshold` 已处理） |
| **GUI 依赖从未实装** | PySide6 / PyInstaller / openpyxl 均**未本机安装验证过** | M5 先 Spike：先在 3.12 通道装 PySide6（`py -3.12 -m pip install PySide6`），实测可 import + offscreen 可跑再定版本 |
| **测试 monkeypatch 引擎函数** | runner 在套件函数内**延迟 import**，运行期打桩可达（M4 探活已验证）；`scan_directory` 内 `import os` 与测试内是同一对象 | 探活/注入类测试用完即还原（try/finally） |

**M0–M4 期未验证的**（M5/M6 才会触到，别当已验证）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收、CI 真跑（无远端）、openpyxl 惰性导入降级真跑。

---

## 五、M5 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M5** 表（M5-1 … M5-12）。逐项要求：

- [ ] M5-1 `engine/pipeline.py` 编排上收为公开函数组；CLI 行为不变（迁移前全绿 = 基线）
- [ ] M5-2 GUI 六页签（自检/岗位应检/档案核查/批量扫描/版本对照/报告导出）
- [ ] M5-3 AST 三条守门（不 import 规则层 + 无 `BinOp` 算术 + 无政策数值字面量）
- [ ] M5-4 三方对账行为等价测试（CLI stdout == pipeline 直调 == 报告章节）
- [ ] M5-5 PySide6 版本按老解释器上限 Spike 实测锁定（3.8 → 6.6.3.1 量级）
- [ ] M5-6 PyInstaller **≥6**（打 GUI 硬下限）
- [ ] M5-7 onedir 双 exe；datas 白名单单一事实源 + 构建后三断言
- [ ] M5-8 冻结态 `--selftest <out.json>`：`frozen=true` + 数据目录落在 dist 内 + 规则数 > 0
- [ ] M5-9 中立目录（Temp + 剥离 PATH）双 exe 验收
- [ ] M5-10 惰性导入 `try` 包住整段；`__import__` 打桩回归 exit 3
- [ ] M5-11 演示素材程序化产出（PNG + GIF），两次生成 sha256 逐个一致
- [ ] M5-12 技术报告 `docs/技术报告.md` 入仓

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8  -X utf8 -m pytest -q                      # 双通道各跑一遍（M4 基线 212 项）
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK（含 clauses.json）
py -3.8  -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8  -X utf8 tools/gen_synthetic.py --check    # FROZEN_TRUTH_OK（74 文件）
py -3.8  -X utf8 tools/check_literals.py --selftest
py -3.8  -X utf8 tools/check_literals.py
py -3.8  -X utf8 -m ohscheck selfcheck
py -3.8  -X utf8 -m ohscheck bench
```

**M5 收尾注意**：GUI 层**不得**出现政策数值字面量（周期月数、切口日等一律从规则包/manifest 取数）；打包后**冻结态产物**由 spec 的 datas 白名单决定，改数据必须走 `tools/gen_*.py` 再重打包，不得手改 dist 内文件。

---

## 六、关键命令速查

```bash
# 环境（Git Bash）
export PYTHONPATH=src                       # 未 pip install -e 时用

# 生成冻结产物（唯一写入者；产物禁手改）
py -3.8 -X utf8 tools/gen_rulesets.py --check    # → data/rules/ + data/knowledge/clauses.json
py -3.8 -X utf8 tools/gen_cases.py --check       # → data/benchmark/
py -3.8 -X utf8 tools/gen_synthetic.py --check   # → data/truth/（74 文件 / 72 档案）

# 门禁
py -3.8 -X utf8 tools/check_literals.py --selftest
py -3.8 -X utf8 tools/check_literals.py

# CLI
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck plan <岗位画像.json>
py -3.8 -X utf8 -m ohscheck check <档案.json>
py -3.8 -X utf8 -m ohscheck scan <档案目录> --baseline <上一轮目录> --out <报告目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck compare
py -3.8 -X utf8 -m ohscheck report <输出目录> --position <岗位.json> --directory <档案目录> --baseline <上一轮目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck bench [--only matrix|coverage|compare|false_positive]
py -3.8 -X utf8 -m ohscheck version

# 测试
py -3.8  -X utf8 -m pytest -q                       # M4 基线：212 项
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 -m pytest -q tests/test_m4.py      # M4 验收门（15 项探活 + 声明 + 结构断言）
py -3.8  -X utf8 -m pytest -q tests/test_truth.py   # 真值库对账

# M5 新增（Spike 期逐步充实）
py -3.12 -m pip install PySide6 "pyinstaller>=6"    # GUI 与打包依赖（3.12 通道）
py -3.12 -X utf8 -m ohscheck gui                    # 桌面界面（缺依赖 → exit 3）
py -3.12 -m PyInstaller packaging.spec              # spec 由 packaging.py 白名单生成（M5-7）
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标（含"未启用"） · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失·溯源断言不满足（拒导） · `3` 缺可选依赖（GUI）。

**M5 调试常用真值件**（同 M3/M4）：

| 因素 | 代码 | 周期 |
|---|---|---|
| 苯 | `GBZ188-5.19` | 12 个月（单值） |
| 铅及其无机化合物 | `GBZ188-5.1` | 分档（`input_required`） |
| 噪声 | `GBZ188-7.1` | 分档（`input_required`） |
| 四乙基铅 | `GBZ188-5.2` | 无在岗期间检查（`kind=none`） |
| 布鲁氏菌（明细 pending） | `GBZ188-8.1` | 门控会拦 |

**报告产物字节可复现**：`scan`/`report` 必须注入 `--generated-at`；`evidence.json` 本身不写时间。
**溯源硬断言**：报告导出前自动执行，不满足抛 `TraceAssertionError`（exit 2），不留半成品（D-64）。
**目录输入指纹**：`export_report` 对目录输入逐文件挂 inputs 指纹。
**基准探活**：改基准输入文件做实验须用临时目录 copytree，**不得动 `data/benchmark/`**。

---

## 七、禁止事项

- **不得手改** `data/rules/`、`data/benchmark/`、`data/truth/`、`data/knowledge/clauses.json` 下任何产物（唯一写入者是 `tools/gen_*.py`）。
- **不得**把 `pending` 条目放进核查路径（门控会拦，别绕过）。
- **不得**在演示/基准/真值库里引入任何真实劳动者信息（虚构姓名代号 + 测试号段）。
- **不得**在公开文档提及姊妹项目业务领域（品牌隔离）。
- **不得**为迁就基准而改真值；分两种情形（plan/05 §2.4）：检查器谓词不自洽 → 只改谓词；口径本身定错 → 引擎与真值**同源修正**，统一验收门 = `gen_synthetic.py --check` 通过 + `tests/test_truth.py` 全绿。
- **不得**把 2014 版当作完整规则源（它是差异导向骨架，决策 D-28）。
- **不得**绕过溯源硬断言导出报告（D-64）。
- **不得**把 `input_required` 与"合规"在报告里同表呈现（D-65）。
- **不得**让 GUI 表现层 import 规则层、写算术或政策数值字面量（M5-3 三守门，plan/04 §十）。
- **不得**用 PyInstaller <6 打 GUI（5.x 确定性崩，D-14）。
- **不得**手改 dist 内冻结产物；数据改动走 `tools/gen_*.py` → 重新打包。
