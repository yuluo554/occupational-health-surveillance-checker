# HANDOFF-M3：批量、对账、报告与证据链（下一棒续接快照）

> **状态**：M2 已完结（2026-10-14），本文件是 M3 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M3.md`，避免入库本机盘符路径）

---

## 一、当前进度（M2 完结实态）

**交付物**：**监护矩阵引擎完整实现**——应检推导（四时点独立）→ 覆盖度四态判定（缺项逐项挂依据）→ 周期判定（三形态 + 边界）→ 别名归一路径 → 溯源硬断言（拒导）→ `input_required` 运行期显式索取；**合成真值 72 件逐件对账 0 不一致**。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **173 项**，Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 5/5、coverage 10/10、compare 3/3、false_positive 误报 0 |
| 官方快照 | `data/knowledge/raw/GBZ188-2025.pdf`（1,553,783 字节，sha256 `5823eea7…`）+ `.layout.txt`（**75,555 汉字**零丢失） |
| 规则包 | `data/rules/`（3 文件）：**2025 版 97 因素**（第 5–7 章 82 因素明细 verified，2520 条 verified）/ **2014 版 81 因素**差异骨架（明细全 pending）；`--check` 再生成逐字节一致 |
| 依据索引 | `data/knowledge/clauses.json`（97 节 + 前言差异 17 条 + 待核对项 4 条）；与规则包同一次 `--check` 守门 |
| 合成真值库 | `data/truth/`（**74 文件**：**72 档案** + truth.json + manifest.json）；自研 splitmix64 seed 20261014；`--check` 位级一致；**72/72 与引擎对账 0 不一致** |
| CI | `.github/workflows/ci.yml`（4 矩阵 + `fetch-depth: 0` + `gen_synthetic.py --check`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M2 完成证据**：`plan/05-数据计划与里程碑.md` §四 M2 DoD 表（7/7 逐项证据 + 实测发现 H-1–H-8）。
**数据台账**：`data/README.md`（14 条 sha256 登记行 + 待核对项 P-1–P-4 状态）。
**M2 决策**：`plan/06` D-61–D-68。

**关键结构事实（M1/M2 实测，务必先读）**：

- GBZ 188—2025 真实章节：**第 5 章化学（5.1–5.65，65 节）/ 第 6 章粉尘（6.1–6.9）/ 第 7 章物理（7.1–7.8）/ 第 8 章生物（8.1–8.5）/ 第 9 章特殊作业（9.1–9.10）**。
- 第 5–7 章（82 因素）**明细已核对**；第 8–9 章（15 因素）**仅因素身份已核对、明细 pending**。
- 周期：**38 因素单值**（12/24/36 月）；**22 因素分档 → `period.status=input_required`**（D-13/D-53/D-62）；**22 因素无在岗期间检查**（`kind=none` → `not_applicable`，D-62）；**15 因素 pending**（第 8–9 章）。
- **三形态各有真值件**（D-61）：`months` → 苯 5.19 / 金属粉尘 6.7 / 激光 7.8；`input_required` → 铅 5.1 / 噪声 7.1 / 矽尘 6.1 / 汞 5.3；`none` → 四乙基铅 5.2。
- 真值件编号：**001–024 算例**，**025–072 批量件**（splitmix64 驱动 48 件）。

---

## 二、M3 待办（按序）

> M3 目标（`plan/05` §四）：**批量扫描失败隔离 + 跨轮对账 + 群体统计 + 报告单一渲染源 + XLSX 逐字节可复现 + 无外链 + 证据链含报告自指纹 + 报告头/参数来源/免责声明/"未启用"显式**。
> **重要**：M3 的**报告层机制大半已在 M0/M2 期锁进测试**（`tests/test_report.py` 9 项 + M2 新增 §4/§5 断言）。M3 的核心增量是 **批量通路的规模验证 + 跨轮对账 + 群体统计可复算**。

### 2.1 M3-1/M3-2 批量扫描失败隔离

| # | 任务 | 判据 |
|---|---|---|
| 1 | `scan` 与 `check` 共用同一分派点 | 已实现（D-32）：`scan_directory` 内调 `check_record`；M3 补**端到端一致性测试**（同档案 `check` 与 `scan` 结论逐字段相同） |
| 2 | 失败件 ≠ 违规锁进测试 | `tests/test_cli.py` 已有 2 项；M3 扩到**全原因码**（`read_error`/`bad_json`/`schema_invalid`/`unknown_factor`/`unknown_exam_type`/`container_too_large`/`gate_blocked`/`missing_input`）逐码有件 |
| 3 | 原因码单列 | 报告 §10 已有；M3 补"逐原因码计数"断言 |

### 2.2 M3-3 跨轮对账

| # | 任务 | 判据 |
|---|---|---|
| 1 | 三主集 + 两辅助集 | `engine/reconcile.py` 已有骨架（`new_missing`/`resolved`/`persistent` + `aux.new_records`/`gone_records`）；M3 补**真值驱动测试** |
| 2 | 配对主键 = `employee_id` + 缺项坐标（**已补齐必须检得出**） | 决策 D-20；M3 必须写"两轮之间补上一项 → `resolved` 检出"的端到端测试（**不得只写不做**） |
| 3 | CLI 通路 | `compare` 已有；`--baseline` 参数**尚未接线**（`report` 的 `reconcile_result` 目前恒 None）→ M3 接线 |

### 2.3 M3-4 群体统计逐项可复算

| # | 任务 | 判据 |
|---|---|---|
| 1 | `sum(明细) == 统计` | `ScanResult.compute_stats()` 已有；M3 补硬断言测试（基准或测试层） |
| 2 | 按因素 / 岗位两维汇总 | 现仅按 `factor_code`；M3 按需加 `position_id` 维 |

### 2.4 M3-5/M3-6/M3-7 报告三性质

| # | 任务 | 判据 |
|---|---|---|
| 1 | 单一渲染源 | `report_sections()` 为唯一结构函数（D-33），已锁；M2 新增 §4 可达性表 / §5 待输入表**自动两格式同步**——M3 补两格式逐项对等断言覆盖新表 |
| 2 | XLSX 逐字节可复现 | 已有实测（D-42）；M3 保持 |
| 3 | 无外链硬断言 | 已有（D-34）；M3 保持 |

### 2.5 M3-8/M3-9 证据链与报告头

| # | 任务 | 判据 |
|---|---|---|
| 1 | 证据链含报告自指纹 | `report/evidence.py` 已有 + `verify_evidence`；M3 补**批量通路**（scan 报告）的指纹测试 |
| 2 | 报告头规则包坐标 + §9 参数来源块 + §11 免责声明 | 已有；M3 保持 |
| 3 | "未启用"章节显式写出 | 已有（D-35）；M2 新增的"周期待输入"表亦须在无数据时显式写"未启用/无数据"（M3 复查） |

### 2.6 M3 收尾

- 回写 `plan/00` 状态表、`plan/05` M3 DoD 逐项证据、`plan/06` 决策记录（M3 新发现）；
- 写 `plan/HANDOFF-M4.md`（六段式）；
- 提交（正常开发流）。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全部落在 `plan/06-决策记录.md` 与 `plan/03`/`plan/04`。此处是**动手前的速查**。
> **M2 新增条目（D-61–D-68）已并入下表**。

| 口径 | 内容 | 落点 |
|---|---|---|
| **版本锚定键 = 体检日期** | `exam_date`（不是编制年度、不是"年度"） | `rules/version.py`；决策 D-10 |
| **年度含切口日即报错** | 只给年度且含切口日 → `AmbiguousYearError` → exit 2，**宁报错不猜** | `rules/version.py`；D-11 |
| **门控按计算路径分作用域** | `plan`/`check` 走 full 深度；`compare`/`bench` 走 minimal；**只拦本次引用到的条目** | `rules/gate.py`；D-12 |
| **门控的阻塞性分级** | `input_required` 分 `blocking`（适用性/项目级→拦）与**非阻塞**（周期级→放行并索取） | `rules/gate.py`；D-53 |
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
| **类别枚举对齐真实章节** | `chemical/physical/dust/biological/special`（第 5–9 章一一对应） | `rules/schema.py`；D-52 |
| **未核对明细不得参与条目级对照** | `compare` 前置 `detail_pending()`：任一侧明细待核对即跳过条目级比较并记 notes | `engine/compare.py`；D-54 |
| **两版节号位移的坐标处置** | 被删的 2014 因素用真实 2014 节号；重号的 2025 镜像因素改占位 `<节号>.0` | `tools/gen_rulesets.py`；D-55 |
| **basis 日期第三态** | `effective_from_status=pending` 时允许 `effective_from` 为空且**禁预填** | `rules/schema.py`；D-56 |
| **真值由独立参考实现算出** | `gen_synthetic.py` 的 `ref_*` **不调引擎**；`tests/test_truth.py` 逐件对账 | `tools/gen_synthetic.py`；D-57 |
| **规则包与依据索引同一生成器** | `clauses.json` 也由 `gen_rulesets.py` 产出，同一次 `--check` | `tools/gen_rulesets.py`；D-58 |
| **不可达算例必须显式声明** | 写入 `data/truth/manifest.json.unreachable_cases`（原因 + 谁覆盖），**不假装覆盖** | `tools/gen_synthetic.py`；D-59 |
| **解析式转写 + 逐字包含断言** | 条文按**条文号索引**切块；每处抽取值断言逐字在快照中 | `tools/gbz188_transcribe.py`；D-60 |
| **周期三形态各有真值件；抽样覆盖须如实登记** ⚠️M2 新 | `months`/`input_required`/`none` 三形态真值库各有覆盖件，测试锁死；manifest `period_shape_coverage` 记"规则包总数 / 采样数 / 清单"（months 38→5、input_required 22→4、none 22→1），写明**抽样非穷举** | `tools/gen_synthetic.py`；D-61 |
| **`kind=none` ≠ `input_required`** ⚠️M2 新 | `none` → `not_applicable`（确无周期要求）；`input_required` → 待输入；**不得合并** | `engine/period.py` + `gen_synthetic.ref_period`；D-62 |
| **缺项依据逐项下钻** ⚠️M2 新 | `ExamPlan.item_bases`/`item_sources`；缺项 finding 挂**项级** basis/source，取不到才回落节级 | `engine/matrix.py` + `engine/coverage.py`；D-63 |
| **溯源硬断言导出前执行、不满足拒导** ⚠️M2 新 | 行数对账 + basis 非空；不满足抛 `TraceAssertionError`（exit 2），**不留半成品报告** | `engine/trace.py` + `engine/export.py`；D-64 |
| **报告把 `input_required` 与"合规"分列** ⚠️M2 新 | §5 单列"周期待输入"表，**不得**与 `compliant` 同表 | `report/sections.py`；D-65 |
| **四态可达性由规则包结构实算并进报告** ⚠️M2 新 | `verdict_reachability(ruleset)`；报告 §4 "四态可达性"表 + 不可达注记 | `engine/coverage.py` + `report/sections.py`；D-66 |
| **覆盖声明可证伪 + 阈值归一 + 未判定≠无义务** ⚠️M2 新 | 覆盖声明须有可证伪测试背书；接触水平与阈值一律 `parse_decimal` 归一后比较；`not_applicable`→`period_verdict=not_applicable`，`input_required`→`period_verdict=input_required`，**不留空** | `engine/matrix.py` + `engine/coverage.py` + `tools/gen_cases.py`；D-68 |
| **报告章节须合并呈现批量通路判定** ⚠️M2 新 | §4/§5/§8 取数面 = `coverage_results + scan_result.items` 合并；**不得**只读 `coverage_results` | `report/sections.py`；D-67 |
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |

---

## 四、本机环境坑（**只写实测过的**）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **Git Bash `/tmp` 与 Windows Python 不通** | `py -3.8 - <<PY` 里写 `/tmp/x` → `FileNotFoundError` | 临时目录用**仓库树外的 Windows 路径**（如 `D:/.../\_m2_scratch`），用完即删 |
| **`py -0p` 有两条通道** | 3.8.8 与 3.12 都装着 → 双通道各跑一遍 | 本项目两者都能跑；M5 打包固定用 **3.12**（PyInstaller ≥6，见 D-14） |
| **中文控制台编码** | 本机一律 `py -3.8 -X utf8` 跑命令 | 但 `-X utf8` 会**整体掩盖**代码里的非 ASCII 输出缺口 → 故入口都装 `_ensure_utf8_stdio()`，并有 cp1252 复现测试 |
| **`json.dumps` 不能直接序列化 Decimal** | 载入用了 `parse_float=Decimal`，测试里改数据后写回会 `TypeError` | 测试一律用 `ohscheck.loaders.dumps_stable` |
| **零字面量门禁会扫中文注释** | 文档里写"2025 年"也会被扫 | 口径写死：中文说明性散文豁免；代码语法里的年份报错（D-27/D-49） |
| **嵌套引号在 heredoc 里易崩** | `py -3.8 - <<'PY'` 里写中文全角引号会 SyntaxError | 长中文补丁走**临时 .py 文件**（放仓库树外），跑完即删 |
| **Windows 路径拼接** | `os.path.join` + `.replace('\\','/')` 在 heredoc 里易转义出错 | 用 `os.path.relpath(p).replace(os.sep,'/')` |
| **测试临时目录里改规则包后 manifest sha 失配** | `make_temp_data_dir` 写 manifest 时填了真实 sha256；测试里改规则包内容会与 manifest 不符 | 若测试不验指纹，可忽略；验指纹时须同步重算（M3 跨轮对账测试注意） |
| **pyc 偶发损坏** | M0/M1/M2 期未出现 | 出怪错先清 `__pycache__` 再跑；单轮崩溃直接重试 |

**M0/M1/M2 期未验证的**（M5 才会触到，别当已验证）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收、CI 真跑（无远端）。

---

## 五、M3 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M3** 表（M3-1 … M3-9）。逐项要求：

- [ ] M3-1 批量扫描失败隔离 + 原因码单列；`scan` 与 `check` 共用同一分派点
- [ ] M3-2 失败件 ≠ 违规（不改变退出码）锁进测试
- [ ] M3-3 跨轮对账三主集 + 两辅助集，配对主键 = `employee_id`（**已补齐必须检得出**）
- [ ] M3-4 群体统计与明细逐项可复算（`sum(明细) == 统计`）
- [ ] M3-5 报告单一渲染源：Markdown + XLSX 逐项对等断言
- [ ] M3-6 XLSX 逐字节可复现（**两次导出 sha256 实测一致**，不得只写不做）
- [ ] M3-7 无外链硬断言（Markdown 正文无 http；XLSX 无外部关系 + 无 `w:hyperlink`）
- [ ] M3-8 证据链含报告自指纹（改动报告即检出）
- [ ] M3-9 报告头规则包坐标 + §9 参数来源块 + §11 免责声明；"未启用"章节显式写出

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8  -X utf8 -m pytest -q                      # 双通道各跑一遍（M2 基线 173 项）
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK（含 clauses.json）
py -3.8  -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8  -X utf8 tools/gen_synthetic.py --check    # FROZEN_TRUTH_OK（M2 起 74 文件）
py -3.8  -X utf8 tools/check_literals.py --selftest
py -3.8  -X utf8 tools/check_literals.py
py -3.8  -X utf8 -m ohscheck selfcheck
py -3.8  -X utf8 -m ohscheck bench
```

**M3 收尾注意**：引擎改动**不得**改真值去凑（`plan/05` §2.4 两种情形判别：
"错的是校验方式还是被校验的口径？"）。判据 = `gen_synthetic.py --check` 仍通过
+ `tests/test_truth.py` 全绿。M2 的 H-1 是**情形一**（参考实现谓词不自洽 → 只改参考实现）。

---

## 六、关键命令速查

```bash
# 环境（Git Bash）
export PYTHONPATH=src                       # 未 pip install -e 时用；建议直接 pip install -e ".[dev]"

# 生成冻结产物（唯一写入者；产物禁手改）
py -3.8 -X utf8 tools/gen_rulesets.py            # → data/rules/ + data/knowledge/clauses.json
py -3.8 -X utf8 tools/gen_cases.py               # → data/benchmark/
py -3.8 -X utf8 tools/gen_synthetic.py           # → data/truth/（74 文件 / 72 档案）
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
py -3.8  -X utf8 -m pytest -q                       # M2 基线：173 项
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 -m pytest -q tests/test_m2.py      # M2 主验收门（27 项）
py -3.8  -X utf8 -m pytest -q tests/test_truth.py   # 真值库对账（M1 门，M2 扩）
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标 · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失·**溯源断言不满足（拒导）** · `3` 缺可选依赖（GUI）。

**真实数据可用因素代码**（M3 调试常用）：

| 因素 | 代码 | 周期 |
|---|---|---|
| 苯 | `GBZ188-5.19` | 12 个月（单值） |
| 金属及其化合物粉尘 | `GBZ188-6.7` | 24 个月（单值） |
| 激光 | `GBZ188-7.8` | 36 个月（单值） |
| 铅及其无机化合物 | `GBZ188-5.1` | 按血铅/尿铅分档（`input_required`） |
| 噪声 | `GBZ188-7.1` | 按等效声级分档（`input_required`） |
| 游离二氧化硅粉尘 | `GBZ188-6.1` | 按生产性粉尘作业分级分档 |
| 汞及其无机化合物 | `GBZ188-5.3` | 按有毒作业分级分档 |
| 四乙基铅 | `GBZ188-5.2` | **无在岗期间检查**（`kind=none`） |
| 布鲁氏菌（明细 pending） | `GBZ188-8.1` | 门控会拦 |

**报告产物字节可复现的用法**：`report` 必须注入 `--generated-at`（否则报告头时间随运行变，破坏同输入同字节）；`evidence.json` 本身**不写时间**。
**溯源硬断言**：报告导出前自动执行；若 `plan.trace` 被破坏会抛 `TraceAssertionError`（exit 2），**不产出任何报告文件**（M2-6/D-64）。

---

## 七、禁止事项

- **不得手改** `data/rules/`、`data/benchmark/`、`data/truth/`、`data/knowledge/clauses.json` 下任何产物（唯一写入者是 `tools/gen_*.py`）。
- **不得**把 `pending` 条目放进核查路径（门控会拦，别绕过）。
- **不得**在演示/基准/真值库里引入任何真实劳动者信息（虚构姓名代号 + 测试号段）。
- **不得**在公开文档提及姊妹项目业务领域（品牌隔离）。
- **不得**为迁就引擎而改真值；分两种情形（`plan/05` §2.4）：检查器谓词不自洽 → 只改谓词；口径本身定错 → 引擎与真值**同源修正**，统一验收门 = `gen_synthetic.py --check` 通过 + `tests/test_truth.py` 全绿。
- **不得**把 2014 版当作完整规则源（它是差异导向骨架，决策 D-28）；**不得**让 compare 报出"因未核对而空"的条目级差异（D-54 已结构性阻断）。
- **不得**绕过溯源硬断言导出报告（D-64：不满足即拒导，别改成"带警告继续"）。
- **不得**把 `input_required` 与"合规"在报告里同表呈现（D-65）。
