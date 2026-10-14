# HANDOFF-M4：内置基准（下一棒续接快照）

> **状态**：M3 已完结（2026-10-14），本文件是 M4 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M4.md`，避免入库本机盘符路径）

---

## 一、当前进度（M3 完结实态）

**交付物**：**批量通路规模验证 + 跨轮对账 + 群体统计可复算**——8 原因码逐码有件且失败隔离；`scan`/`report` 的 `--baseline` 全链路接线（§7 对账章节真实产出）；真值驱动"已补齐 → resolved 检出"端到端（72 件真值档案双轮实跑：resolved 1 项精确命中 / new_missing 0 / persistent 106）；群体统计按因素/岗位两维可复算 + `detail_sha256` 明细绑定；报告三性质（单一渲染源逐项对等 / 逐字节可复现 / 无外链）在批量通路实测；证据链自指纹在批量通路实测（MD/XLSX 双侧篡改检出）。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **197 项**（M2 基线 173 + 新增 `tests/test_m3.py` 24 项），Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 5/5、coverage 13/13、compare 3/3、false_positive 误报 0 |
| 官方快照 | `data/knowledge/raw/GBZ188-2025.pdf`（1,553,783 字节，sha256 `5823eea7…`）+ `.layout.txt`（**75,555 汉字**零丢失） |
| 规则包 | `data/rules/`（3 文件）：**2025 版 97 因素**（第 5–7 章 82 因素明细 verified，2520 条 verified）/ **2014 版 81 因素**差异骨架（明细全 pending）；`--check` 再生成逐字节一致 |
| 依据索引 | `data/knowledge/clauses.json`（97 节 + 前言差异 17 条 + 待核对项 4 条）；与规则包同一次 `--check` 守门 |
| 合成真值库 | `data/truth/`（**74 文件**：72 档案 + truth.json + manifest.json）；自研 splitmix64 seed 20261014；`--check` 位级一致；**72/72 与引擎对账 0 不一致** |
| CI | `.github/workflows/ci.yml`（4 矩阵 + `fetch-depth: 0` + `gen_synthetic.py --check`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M3 完成证据**：`plan/05-数据计划与里程碑.md` §四 M3 DoD 表（9/9 逐项证据 + 实测发现 I-1–I-3）。
**M3 决策**：`plan/06` D-69–D-73。

**关键结构事实（M1/M2/M3 实测，务必先读）**：

- GBZ 188—2025 真实章节：**第 5 章化学（5.1–5.65，65 节）/ 第 6 章粉尘（6.1–6.9）/ 第 7 章物理（7.1–7.8）/ 第 8 章生物（8.1–8.5）/ 第 9 章特殊作业（9.1–9.10）**。
- 第 5–7 章（82 因素）**明细已核对**；第 8–9 章（15 因素）**仅因素身份已核对、明细 pending**。
- 周期：**38 因素单值**（12/24/36 月）；**22 因素分档 → `period.status=input_required`**（D-13/D-53/D-62）；**22 因素无在岗期间检查**（`kind=none` → `not_applicable`，D-62）；**15 因素 pending**（第 8–9 章）。
- **M3 起报告取数面**：§4/§5/§8 = `coverage_results + scan_result.items` 合并（D-67）；§6 统计两维（`by_factor` + `by_position`）+ `detail_sha256`（D-69）；§7 对账由 `--baseline` 驱动（D-70），`content_changed` 单列（D-20/D-70）。
- **`CoverageResult` 新增 `position_id`**（D-69）；`ScanResult.stats` 新增 `detail_sha256` 与 `by_position`（D-69）——消费统计的代码不得假设旧形状。
- **失败件原因码全 8 个**（`errors.py`）：`read_error`/`bad_json`/`schema_invalid`/`unknown_factor`/`unknown_exam_type`/`container_too_large`/`gate_blocked`/`missing_input`——`read_error` 在 M3 修复（I-1/D-71），`missing_input` 走"适用性待输入"夹具。
- 真值件编号：**001–024 算例**，**025–072 批量件**（splitmix64 驱动 48 件）。

---

## 二、M4 待办（按序）

> M4 目标（`plan/05` §四）：**内置基准四套件 + 可证伪探活 + 门槛随 manifest 下发 + 指标入 README + "未启用"套件如实声明**。
> **重要**：M4 的**骨架已在 M0/M2 期就位**——`ohscheck bench` 四套件（matrix/coverage/compare/false_positive）已全达标、`--only` 白名单已实现、门槛读 `manifest.benchmark_thresholds`（D-24/D-25）、`benchmark/cases.py` 是对账口径单一实现源。M4 的核心增量是 **M4-3 可证伪探活（注入缺陷 → 必须报未达标）与 M4-5/M4-6 指标入 README + 未启用声明**。

### 2.1 M4-1/M4-2 套件与两层驱动

| # | 任务 | 判据 |
|---|---|---|
| 1 | 四套件 + `--only` 白名单 | 已实现（D-25：未知名 → exit 2）；M4 复查样本驱动（读真值库）与规则驱动（不读真值库）两层是否齐备，缺则补 |
| 2 | 基准数据与生产数据分离 | 已实现（D-51：`data/benchmark/` 合成规则集，`SYNTHETIC-` 结构护栏）；M4 补"基准不读 `data/truth/` 之外的真实档案"的结构断言（若缺） |

### 2.2 M4-3 可证伪探活（本里程碑核心增量）

| # | 任务 | 判据 |
|---|---|---|
| 1 | 每套件注入缺陷 → 必须报未达标 | 对 matrix/coverage/compare/false_positive 各写一个"探活测试"：在测试内构造**缺陷版**输入（如真值翻转、阈值抬高），断言基准层报"未达标"（exit 1）——**基准会绿也会红，只会绿的基准是假基准** |
| 2 | 探活不得污染正常基准 | 探活用测试内夹具/临时目录，不动 `data/benchmark/` 冻结产物 |

### 2.3 M4-4 门槛随 manifest（已实现，复查）

- `manifest.benchmark_thresholds` 缺失 → exit 2（D-24）；`--only` 未知名 → exit 2（D-25）。M4 补缺失场景的端到端测试（若缺）。

### 2.4 M4-5/M4-6 指标入 README + 未启用声明

| # | 任务 | 判据 |
|---|---|---|
| 1 | 指标写入 README | 正确率 / 误报数 / 运行时长**实测值**写进 README（跑 `ohscheck bench` 取实测，不编造） |
| 2 | "未启用"套件如实声明 | 若某类用例未生成，基准输出写明"该类用例未生成"，不假装覆盖（D-59 同族）；M0 期 `eligibility_coverage`/`period_shape_coverage` 的登记口径沿用 |

### 2.5 M4 收尾

- 回写 `plan/00` 状态表、`plan/05` M4 DoD 逐项证据、`plan/06` 决策记录（M4 新发现）；
- 写 `plan/HANDOFF-M5.md`（六段式）；
- 提交（正常开发流）。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全部落在 `plan/06-决策记录.md` 与 `plan/03`/`plan/04`。M3 新增 D-69–D-73 已并入决策表；
> **本节只列与 M4 直接相关的**，全量口径速查见 `plan/HANDOFF-M3.md` §三（历史快照）或 `plan/06`。

| 口径 | 内容 | 落点 |
|---|---|---|
| **门槛随 manifest 下发** | 基准门槛读 `manifest.benchmark_thresholds`，缺失即 exit 2，**不回落代码默认值** | `benchmark/runner.py`；D-24 |
| **`--only` 未知名 → exit 2** | 不许静默跳过 | `benchmark/runner.py`；D-25 |
| **基准验机制、不验国标内容** | `data/benchmark/` 用合成规则集（`synthetic=true`、`SYNTHETIC-` 前缀、`issuer` 为空），与生产规则包分离 | `benchmark/`；D-51 |
| **对账口径单一实现源** | `benchmark/cases.py` 的 `compare_expected` 供测试与基准共用，不得复制第二份 | `benchmark/cases.py`；D-20/05 §2.4 |
| **真值由独立参考实现算出** | `gen_synthetic.py` 的 `ref_*` 不调引擎；`tests/test_truth.py` 逐件对账 | `tools/gen_synthetic.py`；D-57 |
| **不可达算例必须显式声明** | 写入 `data/truth/manifest.json.unreachable_cases` + `eligibility_coverage`（M3 期可证伪测试背书） | `tools/gen_synthetic.py`；D-59 |
| **失败件 ≠ 违规** | 基准通路同样适用：failed 件不计入"检出不符合" | `engine/scan.py`；D-21 |
| **不适用 ≠ 违规** | `not_applicable` 不计入 exit 1；`unknown` 不降级为 `compliant`（`observed_nonpass` 排除 not_applicable） | `benchmark/cases.py`；D-22 |
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |

---

## 四、本机环境坑（**只写实测过的**；全量见 `plan/HANDOFF-M3.md` §四）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **heredoc 里的非 ASCII** | `py -3.8 - <<'PY'` 内联中文补丁偶发编码报错（Non-UTF-8 声明缺失） | 长中文补丁走**临时 .py 文件**（放仓库树外，如 `<workdir>/_m4_scratch.py`），首行 `# -*- coding: utf-8 -*-`，跑完即删 |
| **嵌套函数级 monkeypatch** | `scan_directory` 内 `import os` 的模块引用与测试内 `import os` 是同一对象 → patch `scan_mod.os.path.getsize` 会波及全局 | 探活/注入类测试用**完即还原**（try/finally），或改打桩 `provider` |
| **测试临时目录里改规则包后 manifest sha 失配** | `make_temp_data_dir` 写 manifest 时填了真实 sha256 | 测试不验指纹可忽略；验指纹须同步重算 |
| **Git Bash `/tmp` 与 Windows Python 不通** | heredoc 里写 `/tmp/x` → FileNotFoundError | 临时目录用仓库树外 Windows 路径 |
| **`py -0p` 有两条通道** | 3.8.8 与 3.12 并存 | 双通道各跑一遍；M5 打包固定 3.12（D-14） |
| **json.dumps 不能直接序列化 Decimal** | 载入 `parse_float=Decimal` 后改数据写回会 TypeError | 测试用 `ohscheck.loaders.dumps_stable` |

**M0–M3 期未验证的**（M5/M6 才会触到，别当已验证）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收、CI 真跑（无远端）。

---

## 五、M4 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M4** 表（M4-1 … M4-6）。逐项要求：

- [ ] M4-1 四套件 + `--only` 白名单（复查既有 + 补缺）
- [ ] M4-2 样本驱动 + 规则驱动两层（规则驱动不读真值库）
- [ ] M4-3 每套件可证伪探活（注入缺陷 → 必须报未达标）——**本里程碑核心增量，不得只写不做**
- [ ] M4-4 门槛随 manifest 下发，缺失即退出码 2（补端到端测试）
- [ ] M4-5 指标写入 README（实测值，不编造）
- [ ] M4-6 "未启用"套件如实声明

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8  -X utf8 -m pytest -q                      # 双通道各跑一遍（M3 基线 197 项）
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK（含 clauses.json）
py -3.8  -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8  -X utf8 tools/gen_synthetic.py --check    # FROZEN_TRUTH_OK（74 文件）
py -3.8  -X utf8 tools/check_literals.py --selftest
py -3.8  -X utf8 tools/check_literals.py
py -3.8  -X utf8 -m ohscheck selfcheck
py -3.8  -X utf8 -m ohscheck bench
```

**M4 收尾注意**：基准层改动**不得**改真值去凑（plan/05 §2.4 两种情形判别）。
判据 = `gen_synthetic.py --check` 仍通过 + `tests/test_truth.py` 全绿 + `bench` 四套件
退出码 0。**探活测试证明基准"会红"是 M4 的主验收门**——只会绿的基准视为未实现。

---

## 六、关键命令速查

```bash
# 环境（Git Bash）
export PYTHONPATH=src                       # 未 pip install -e 时用

# 生成冻结产物（唯一写入者；产物禁手改）
py -3.8 -X utf8 tools/gen_rulesets.py            # → data/rules/ + data/knowledge/clauses.json
py -3.8 -X utf8 tools/gen_cases.py               # → data/benchmark/
py -3.8 -X utf8 tools/gen_synthetic.py           # → data/truth/（74 文件 / 72 档案）
py -3.8 -X utf8 tools/gen_rulesets.py --check
py -3.8 -X utf8 tools/gen_cases.py --check
py -3.8 -X utf8 tools/gen_synthetic.py --check

# 门禁
py -3.8 -X utf8 tools/check_literals.py --selftest
py -3.8 -X utf8 tools/check_literals.py

# CLI
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck plan <岗位画像.js
py -3.8 -X utf8 tools/gen_rulesets.py --check
py -3.8 -X utf8 tools/gen_cases.py --check
py -3.8 -X utf8 tools/gen_synthetic.py --check

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
py -3.8  -X utf8 -m pytest -q                       # M3 基线：197 项
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 -m pytest -q tests/test_m3.py      # M3 验收门（24 项）
py -3.8  -X utf8 -m pytest -q tests/test_truth.py   # 真值库对账
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标 · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失·溯源断言不满足（拒导） · `3` 缺可选依赖（GUI）。

**M4 调试常用真值件**（同 M3）：

| 因素 | 代码 | 周期 |
|---|---|---|
| 苯 | `GBZ188-5.19` | 12 个月（单值） |
| 铅及其无机化合物 | `GBZ188-5.1` | 分档（`input_required`） |
| 噪声 | `GBZ188-7.1` | 分档（`input_required`） |
| 四乙基铅 | `GBZ188-5.2` | 无在岗期间检查（`kind=none`） |
| 布鲁氏菌（明细 pending） | `GBZ188-8.1` | 门控会拦 |

**报告产物字节可复现**：`scan`/`report` 必须注入 `--generated-at`；`evidence.json` 本身不写时间。
**溯源硬断言**：报告导出前自动执行，不满足抛 `TraceAssertionError`（exit 2），不留半成品（D-64）。
**目录输入指纹**（M3 起）：`export_report` 对目录输入逐文件挂 inputs 指纹——改基准输入文件会破坏 evidence 一致性，探活测试须用独立输出目录。

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
- **不得**让探活测试污染冻结产物（`data/benchmark/` 只读；探活用测试夹具）。
