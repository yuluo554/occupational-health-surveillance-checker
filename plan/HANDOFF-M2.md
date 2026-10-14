# HANDOFF-M2：监护矩阵引擎与覆盖度判定（下一棒续接快照）

> **状态**：M1 已完结（2026-10-14），本文件是 M2 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M2.md`，避免入库本机盘符路径）

---

## 一、当前进度（M1 完结实态）

**交付物**：**真实数据已入库**——官方原文快照 + 逐条转写的双版本规则包 + 依据索引 + 合成真值库；引擎骨架在真实数据上跑通（plan/check/scan/compare/report/bench 全通路）。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **146 项**，Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 5/5、coverage 10/10、compare 3/3、false_positive 误报 0 |
| 官方快照 | `data/knowledge/raw/GBZ188-2025.pdf`（1,553,783 字节，sha256 `5823eea7…`）+ `GBZ188-2025.layout.txt`（**75,555 汉字**零丢失） |
| 规则包 | `data/rules/`（3 文件）：**2025 版 97 因素**（第 5–7 章 82 因素明细 verified，2520 条 verified）/ **2014 版 81 因素**差异骨架（明细全 pending）；`--check` 再生成逐字节一致 |
| 依据索引 | `data/knowledge/clauses.json`（97 节 + 前言差异 17 条 + 待核对项 4 条）；与规则包同一次 `--check` 守门 |
| 合成真值库 | `data/truth/`（**70 文件**：68 档案 + truth.json + manifest.json）；自研 splitmix64 seed 20261014；`--check` 位级一致；**68/68 与引擎对账 0 不一致** |
| CI | `.github/workflows/ci.yml`（4 矩阵 + `fetch-depth: 0` + 新增 `gen_synthetic.py --check`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M1 完成证据**：`plan/05-数据计划与里程碑.md` §四 M1 DoD 表（7/7 逐项证据 + 实测发现 G-1–G-7）。
**数据台账**：`data/README.md`（14 条 sha256 登记行 + 待核对项 P-1–P-4 状态）。

**关键结构事实（M1 实测，务必先读）**：

- GBZ 188—2025 真实章节：**第 5 章化学（5.1–5.65，65 节）/ 第 6 章粉尘（6.1–6.9）/ 第 7 章物理（7.1–7.8）/ 第 8 章生物（8.1–8.5）/ 第 9 章特殊作业（9.1–9.10）**。M0 骨架曾误标第 6 章为物理（发现 G-1）。
- 第 5–7 章（82 因素）**明细已核对**；第 8–9 章（15 因素）**仅因素身份已核对、明细 pending**——这是 M1-7 已验证的"部分核对"混合态。
- 周期：38 因素落**单值**（12/24/36 月）；**22 因素按作业分级/接触水平分档 → `period.status=input_required`**（决策 D-13/D-53）；22 因素**无在岗期间检查**（`kind=none`）；15 因素 pending（第 8–9 章）。

---

## 二、M2 待办（按序）

> M2 目标（`plan/05` §四）：**监护矩阵引擎完整实现 + 覆盖度四态判定 + 周期边界 + 别归一 + 溯源硬断言 + input_required 运行期显式索取**，合成真值对账 100%。
> **重要**：M1 已把真值库建好（68 件，独立参考实现）；M2 的验收门就是"引擎与真值 100% 对账"——`tests/test_truth.py` 的逐件对账测试已经是这个门的**当前形态**，M2 只需把覆盖面扩到 DoD 各项。

### 2.1 M2-1/M2-2 矩阵推导完善

| # | 任务 | 判据 |
|---|---|---|
| 1 | `compute_plan` 四时点独立判定（不互相污染） | 每时点独立取 `examinations[时点]`；补测试断言"改一个时点不影响其他三个" |
| 2 | 适用性三态在真实数据上正确 | 真实包全 `kind=always`（标准对所列因素"接触即纳入"）；机制分支由 `data/benchmark/` 合成夹具覆盖（threshold / input_required） |
| 3 | 周期分档的**运行期显式索取** | `period.status=input_required` → 放行 + 记 `missing_inputs`（`blocking=False`）；报告须呈现"待输入"而非"合规"（决策 D-13/D-53） |

**注意**：M1 已改过门控与 pipeline（发现 G-2）——`missing_inputs` 现在带 `blocking` 字段。**改这里前先读 `rules/gate.py` 的 `_collect_full/_collect_minimal` 与 `engine/pipeline.py` 的 `_blocking_inputs`**。

### 2.2 M2-3 覆盖度四态 + 缺项挂 basis

| # | 任务 | 判据 |
|---|---|---|
| 1 | 四态定级边界在真实数据上锁死 | `compliant`/`partial`/`non_compliant`/`not_applicable` 逐档有真值件覆盖（`data/truth/manifest.json.coverage_matrix` 已列） |
| 2 | 缺项挂 basis（逐项可下钻） | 现 `_item_basis` 返回**节级** basis；M2 可按需下钻到 `item.source`（规则包已逐项挂 source） |
| 3 | `not_applicable` 的**如实声明** | 真实包不可达（见 `data/truth/manifest.json.unreachable_cases`）——报告须写明"未覆盖"而非假装覆盖（决策 D-59） |

### 2.3 M2-4 周期边界

| # | 任务 | 判据 |
|---|---|---|
| 1 | `due` 计入合规、月末夹取、`no_baseline` | `tests/test_engine.py` 已有 4 项；M1 真值库另有 5 件边界档案（`SYN-TRUTH-012/013/014/015/019` 等） |
| 2 | **分档周期不误报超期** | M1 已锁：`period_verdict=input_required` 且 `verdict=compliant`（`test_real_ruleset_period_verdict_reports_input_required_not_overdue`） |
| 3 | 真实数据的周期覆盖 | 38 单值因素 + 22 分档因素 + 22 无周期因素，各有真值件或显式声明 |

### 2.4 M2-5 别名归一路径

| # | 任务 | 判据 |
|---|---|---|
| 1 | 别名表 pending 时**整体禁用**（不猜） | 现有实现：`pipeline._alias_map` 在 `status != verified` 时返回 `None` |
| 2 | **M1 起可考虑启用别名表** | 真实项目名已入库（`item_code == item_name == 标准原文写法`）；若要做别名表，**必须是显式表**（禁模糊匹配，决策 D-17），并配误报对照 |
| 3 | 归一失败降级 warning 不判缺 | 真值库有 1 件（`SYN-TRUTH-020`）；测试 `test_alias_written_but_clean_record_degrades_to_warning_not_failure` |

### 2.5 M2-6 溯源硬断言

| # | 任务 | 判据 |
|---|---|---|
| 1 | 行数对账 + basis 非空 | `len(trace) >= len(明细行) + len(因素行)`；每条 trace 的 basis 非空；不满足**拒导** |
| 2 | 逐项依据可追 | 规则包 `required_items[].source` 已逐项挂节号（M1 已实现），M2 把它透到 trace/报告 |

### 2.6 M2-7 `input_required` 运行期显式索取

| # | 任务 | 判据 |
|---|---|---|
| 1 | 缺失即退出码 2，绝不静默取默认 | `MissingInputError` 通路已锁；M2 补 CLI 端到端测试（真实数据上引用分档因素） |
| 2 | 报告呈现"待输入" | 报告 §5 周期合规须把 `input_required` 单列，**不得**与"合规"混同 |

### 2.7 M2 收尾

- 回写 `plan/00` 状态表、`plan/05` M2 DoD 逐项证据、`plan/06` 决策记录（M2 新发现）；
- 写 `plan/HANDOFF-M3.md`（六段式）；
- 提交（正常开发流）。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全部落在 `plan/06-决策记录.md` 与 `plan/03`/`plan/04`。此处是**动手前的速查**。
> **M1 新增条目（D-52–D-60）已并入下表**。

| 口径 | 内容 | 落点 |
|---|---|---|
| **版本锚定键 = 体检日期** | `exam_date`（不是编制年度、不是"年度"） | `rules/version.py`；决策 D-10 |
| **年度含切口日即报错** | 只给年度且含切口日 → `AmbiguousYearError` → exit 2，**宁报错不猜** | `rules/version.py`；D-11 |
| **门控按计算路径分作用域** | `plan`/`check` 走 full 深度；`compare`/`bench` 走 minimal；**只拦本次引用到的条目** | `rules/gate.py`；D-12 |
| **门控的阻塞性分级** ⚠️M1 新 | `input_required` 分 `blocking`（适用性/项目级→拦）与**非阻塞**（周期级→放行并索取） | `rules/gate.py`；D-53 |
| **第三态 `input_required`** | 放行门控但运行时**必索**，缺失即 exit 2，**绝不静默取默认值** | `rules/gate.py` + `pipeline`；D-13 |
| **应检项集 = 仅必检项** | `expected = required_items`；补充/选检项**不进判定** → **工具不做"补充检查合规"判定** | `engine/matrix.py`；D-16 |
| **别名归一禁模糊匹配** | 必须是显式别名表；不成立 → 记 `unmapped_item` 并降级 **warning 而非 fail** | `engine/coverage.py`；D-17 |
| **周期判定不用"今天"** | 判据 = `current` vs `last + N 月`；`due` 当日**计入合规**；无基线 → `no_baseline` **不报超期** | `engine/period.py`；D-18 |
| **月加法月末夹取** | 自写 `add_months`（不引 dateutil）；1/31+1月 → 2/28 或 2/29 | `engine/period.py`；D-19 |
| **对账配对主键 = 稳定身份键** | `employee_id` + 缺项坐标，**不是内容指纹** | `engine/reconcile.py`；D-20 |
| **失败件 ≠ 违规** | 坏 JSON/超大输入 → `failed` + 原因码，**不改变退出码**；单列不静默吞 | `engine/scan.py`；D-21 |
| **不适用 ≠ 违规** | `not_applicable` 不计入 exit 1；`unknown` 不降级为 `compliant` | `engine/coverage.py`；D-22 |
| **门槛随 manifest 下发** | 基准门槛读 `manifest.benchmark_thresholds`，缺失即 exit 2，**不回落代码默认值** | `benchmark/runner.py`；D-24 |
| **`--only` 未知名 → exit 2** | 不许静默跳过 | `benchmark/runner.py`；D-25 |
| **单件与批量共用分派点** | `check` 与 `scan` 走**同一个** `check_record()` | `engine/pipeline.py`；D-32 |
| **报告单一渲染源** | `report_sections()` 为唯一章节结构函数，MD/XLSX 都消费它 | `report/sections.py`；D-33 |
| **无外链断言口径** | Markdown 正文无 `](`；XLSX 无 `TargetMode="External"`/无 `w:hyperlink`；**不对 `.rels` 全文做 http 扫描** | `tests/test_report.py`；D-34 |
| **"未启用"章节显式写出** | 留空会被误读成"查了没问题" | `report/sections.py`；D-35 |
| **数据定位优先级** | 显式 > `OHSCHECK_DATA_DIR` > 冻结态分支 > 源码态上溯 | `paths.py`；D-36 |
| **零字面量门禁豁免口径** | 数值只能来自规则包；**中文说明性散文里的年份豁免**，代码语法里的报错 | `tools/check_literals.py`；D-27 |
| **选检项目口径是数据** | `optional_items_policy: any \| emergency_only`，**不在代码里按版本号硬编码** | `rules/schema.py`；D-46 |
| **类别枚举对齐真实章节** ⚠️M1 新 | `chemical/physical/dust/biological/special`（第 5–9 章一一对应） | `rules/schema.py`；D-52 |
| **未核对明细不得参与条目级对照** ⚠️M1 新 | `compare` 前置 `detail_pending()`：任一侧明细待核对即跳过条目级比较并记 notes | `engine/compare.py`；D-54 |
| **两版节号位移的坐标处置** ⚠️M1 新 | 被删的 2014 因素用真实 2014 节号；重号的 2025 镜像因素改占位 `<节号>.0` | `tools/gen_rulesets.py`；D-55 |
| **basis 日期第三态** ⚠️M1 新 | `effective_from_status=pending` 时允许 `effective_from` 为空且**禁预填** | `rules/schema.py`；D-56 |
| **真值由独立参考实现算出** ⚠️M1 新 | `gen_synthetic.py` 的 `ref_*` **不调引擎**；`tests/test_truth.py` 逐件对账 | `tools/gen_synthetic.py`；D-57 |
| **规则包与依据索引同一生成器** | `clauses.json` 也由 `gen_rulesets.py` 产出，同一次 `--check` | `tools/gen_rulesets.py`；D-58 |
| **不可达算例必须显式声明** ⚠️M1 新 | 写入 `data/truth/manifest.json.unreachable_cases`（原因 + 谁覆盖），**不假装覆盖** | `tools/gen_synthetic.py`；D-59 |
| **解析式转写 + 逐字包含断言** | 条文按**条文号索引**切块（非行序启发式）；每处抽取值断言逐字在快照中 | `tools/gbz188_transcribe.py`；D-60 |
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |

---

## 四、本机环境坑（**只写实测过的**）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **Git Bash `/tmp` 与 Windows Python 不通** | `py -3.8 - <<PY` 里写 `/tmp/x` → `FileNotFoundError` | 临时目录用**仓库树外的 Windows 路径**（如 `D:/.../\_m1_scratch`），用完即删 |
| **`py -0p` 有两条通道** | 3.8.8 与 3.12 都装着 → 双通道各跑一遍 | 本项目两者都能跑；M5 打包固定用 **3.12**（PyInstaller ≥6，见 D-14） |
| **中文控制台编码** | 本机一律 `py -3.8 -X utf8` 跑命令 | 但 `-X utf8` 会**整体掩盖**代码里的非 ASCII 输出缺口 → 故入口都装 `_ensure_utf8_stdio()`，并有 cp1252 复现测试 |
| **`json.dumps` 不能直接序列化 Decimal** | 载入用了 `parse_float=Decimal`，测试里改数据后写回会 `TypeError` | 测试一律用 `ohscheck.loaders.dumps_stable` |
| **零字面量门禁会扫中文注释** | 文档里写"2025 年"也会被扫（M1 实测扫出 schema.py 一处裸年份） | 口径写死：中文说明性散文豁免；代码语法里的年份报错（D-27/D-49）；M1 已把该处改成中文叙述 |
| **嵌套引号在 heredoc 里易崩** | `py -3.8 - <<'PY'` 里写中文全角引号 `"` 会 SyntaxError | 长中文补丁走**临时 .py 文件**（放仓库树外），跑完即删 |
| **Windows 路径拼接** | `os.path.join` + `.replace('\\','/')` 在 heredoc 里易转义出错 | 用 `os.path.relpath(p).replace(os.sep,'/')` |
| **pyc 偶发损坏** | 未见（M0/M1 期未出现） | 出怪错先清 `__pycache__` 再跑；单轮崩溃直接重试 |

**M0/M1 期未验证的**（M5 才会触到，别当已验证）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收、CI 真跑（无远端）。

---

## 五、M2 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M2** 表（M2-1 … M2-7）。逐项要求：

- [ ] M2-1 `compute_plan` 完整实现，合成真值对账 100%
- [ ] M2-2 四时点独立判定（不互相污染）
- [ ] M2-3 覆盖度四态判定 + 缺项挂 basis，合成植入真值对账 100%
- [ ] M2-4 周期判定含边界（`due` 计入合规、月末夹取、`no_baseline`）
- [ ] M2-5 别名归一路径（含 pending 时整体禁用、禁止模糊匹配）
- [ ] M2-6 溯源硬断言（行数对账 + basis 非空，不满足拒导）
- [ ] M2-7 `input_required` 运行期显式索取（缺失即退出码 2，绝不静默取默认）

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8  -X utf8 -m pytest -q                      # 双通道各跑一遍
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK（含 clauses.json）
py -3.8  -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8  -X utf8 tools/gen_synthetic.py --check    # FROZEN_TRUTH_OK
py -3.8  -X utf8 tools/check_literals.py --selftest
py -3.8  -X utf8 tools/check_literals.py
py -3.8  -X utf8 -m ohscheck selfcheck
py -3.8  -X utf8 -m ohscheck bench
```

**M2 收尾注意**：引擎改动**不得**改真值去凑（`plan/05` §2.4 两种情形判别：
"错的是校验方式还是被校验的口径？"）。判据 = `gen_synthetic.py --check` 仍通过
+ `tests/test_truth.py` 全绿。若确属"口径本身定错" → 引擎与真值**同源修正**。

---

## 六、关键命令速查

```bash
# 环境（Git Bash）
export PYTHONPATH=src                       # 未 pip install -e 时用；建议直接 pip install -e ".[dev]"

# 生成冻结产物（唯一写入者；产物禁手改）
py -3.8 -X utf8 tools/gen_rulesets.py            # → data/rules/ + data/knowledge/clauses.json
py -3.8 -X utf8 tools/gen_cases.py               # → data/benchmark/
py -3.8 -X utf8 tools/gen_synthetic.py           # → data/truth/
py -3.8 -X utf8 tools/gen_rulesets.py --check    # 再生成逐字节一致守门
py -3.8 -X utf8 tools/gen_cases.py --check
py -3.8 -X utf8 tools/gen_synthetic.py --check

# 解析器诊断（只读；--dump 打印指定节次的转写结果）
py -3.8 -X utf8 tools/gbz188_transcribe.py --dump 5.19 7.1

# 门禁
py -3.8 -X utf8 tools/check_literals.py --selftest   # 阳性对照（必先跑）
py -3.8 -X utf8 tools/check_literals.py              # 扫描（0 命中 = exit 0）

# CLI
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck plan <岗位画像.json>      # 例：factors[].factor_code = "GBZ188-5.19"（苯）
py -3.8 -X utf8 -m ohscheck check <档案.json>
py -3.8 -X utf8 -m ohscheck scan <档案目录> --out <报告目录>
py -3.8 -X utf8 -m ohscheck compare
py -3.8 -X utf8 -m ohscheck report <输出目录> --position <岗位.json> --directory <档案目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck bench [--only matrix|coverage|compare|false_positive]
py -3.8 -X utf8 -m ohscheck version

# 测试
py -3.8  -X utf8 -m pytest -q
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 -m pytest -q tests/test_truth.py    # 真值库对账（M2 主验收门）
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标 · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失 · `3` 缺可选依赖（GUI）。

**真实数据可用因素代码**（M2 调试常用）：

| 因素 | 代码 | 周期 |
|---|---|---|
| 苯 | `GBZ188-5.19` | 12 个月（单值） |
| 铅及其无机化合物 | `GBZ188-5.1` | 按血铅/尿铅分档（`input_required`） |
| 噪声 | `GBZ188-7.1` | 按等效声级分档（`input_required`） |
| 高温 | `GBZ188-7.3` | 12 个月（单值） |
| 游离二氧化硅粉尘 | `GBZ188-6.1` | 按生产性粉尘作业分级分档 |
| 布鲁氏菌（明细 pending） | `GBZ188-8.1` | 门控会拦 |

**报告产物字节可复现的用法**：`report` 必须注入 `--generated-at`（否则报告头时间随运行变，破坏同输入同字节）；`evidence.json` 本身**不写时间**。

---

## 七、禁止事项

- **不得手改** `data/rules/`、`data/benchmark/`、`data/truth/`、`data/knowledge/clauses.json` 下任何产物（唯一写入者是 `tools/gen_*.py`）。
- **不得**把 `pending` 条目放进核查路径（门控会拦，别绕过）。
- **不得**在演示/基准/真值库里引入任何真实劳动者信息（虚构姓名代号 + 测试号段）。
- **不得**在公开文档提及姊妹项目业务领域（品牌隔离）。
- **不得**为迁就引擎而改真值；分两种情形（`plan/05` §2.4）：检查器谓词不自洽 → 只改谓词；口径本身定错 → 引擎与真值**同源修正**，统一验收门 = `gen_synthetic.py --check` 通过 + `tests/test_truth.py` 全绿。
- **不得**把 2014 版当作完整规则源（它是差异导向骨架，决策 D-28）；**不得**让 compare 报出"因未核对而空"的条目级差异（D-54 已结构性阻断）。
