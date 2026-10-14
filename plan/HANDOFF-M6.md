# HANDOFF-M6：脱敏发布与收尾（下一棒续接快照）

> **状态**：M5 已完结（2026-10-14），本文件是 M6 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M6.md`，避免入库本机盘符路径）

---

## 一、当前进度（M5 完结实态）

**交付物**：**桌面交付与打包**——`engine/pipeline.py` 编排上收四个公开函数（`scan_with_reconcile`/`generate_report`/`report_from_inputs`/`selfcheck_payload`，CLI `selfcheck/scan/report` 改为消费它们，CLI 端到端输出一字不变）+ **GUI 六页签**（自检/岗位应检/档案核查/批量扫描/版本对照/报告导出；`gui/service.py` 是 GUI 唯一引擎入口，offscreen 冒烟 exit 0）+ **AST 三条守门锁进测试**（不 import 规则层 / 零 `BinOp` / 零政策数值字面量——守门③实装当轮真抓到 placeholder 里的年度数字）+ **三方对账行为等价测试**（真实规则包驱动：CLI stdout == pipeline 直调 == GUI 服务层 == 报告章节）+ **PyInstaller 6.22.3 onedir 双 exe 真构建**（`tools/gen_spec.py` 从 `packaging.DATA_WHITELIST` 生成 spec，`--check` 守门）+ **冻结态 `--selftest` 真跑通过**（`frozen=true` / `data_dir_inside_exe=true` / `ok=true`）+ **中立目录（剥 PATH）双 exe 验收通过** + **演示素材 sha256 可复现**（`tools/gen_demo_assets.py`，六页签 PNG + 轮播 GIF，`--check` 两次生成逐个一致）+ **技术报告入仓**（`docs/技术报告.md` 十章）。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **227 项**（M4 基线 212 + 新增 `tests/test_m5.py` 15 项），Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 1.0000（5+规则驱动 7）、coverage 1.0000（13）、compare 1.0000（3）、false_positive 误报 0（7 件）、运行时长 0.005 秒（上限 5.0） |
| GUI 依赖 | PySide6 **6.6.3.1**（3.12 通道实装；`pip index` 实测 3.8 上限正是 6.6.3.1）——pyproject `gui = ["PySide6>=6.6,<6.7"]` 一致 |
| 打包 | PyInstaller **6.22.3**（3.12 通道）；`tools/packaging.spec`（生成文件，`gen_spec.py --check` 守门）；datas 白名单 = `packaging.DATA_WHITELIST`（**rules/benchmark/truth** 三项；不整仓塞 `data/`） |
| 冻结产物 | `build-m5/dist/ohscheck/`：`ohscheck-gui.exe`（console=False）+ `ohscheck-cli.exe`（console=True）+ `_internal/data`；约 117 MB（**构建目录不入仓**，gitignore 已有 `build*/`） |
| 演示素材 | `docs/assets/`：六页签 PNG + `gui-demo.gif` + `sha256sums.txt`（8 文件，`gen_demo_assets.py --check` 两次生成逐个一致） |
| 技术报告 | `docs/技术报告.md`（十章）；H-6 缓议项已裁决（docx 跳过，D-76） |
| 官方快照 | `data/knowledge/raw/GBZ188-2025.pdf`（1,553,783 字节，sha256 `5823eea7…`）+ `.layout.txt`（75,555 汉字零丢失） |
| 规则包 | `data/rules/`（3 文件）：2025 版 97 因素（第 5–7 章 82 因素明细 verified，2520 条 verified）/ 2014 版 81 因素差异骨架（明细全 pending）；`--check` 再生成逐字节一致 |
| 合成真值库 | `data/truth/`（74 文件：72 档案 + truth.json + manifest.json）；`--check` 位级一致；72/72 与引擎对账 0 不一致 |
| CI | `.github/workflows/ci.yml`（4 矩阵 + `fetch-depth: 0` + `gen_synthetic.py --check`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M5 完成证据**：`plan/05-数据计划与里程碑.md` §四 M5 DoD 表（12/12 逐项证据 + 实测发现 K-1–K-3）。
**M5 决策**：`plan/06` D-76–D-79。

**关键结构事实（M1–M5 实测，务必先读）**：

- GBZ 188—2025 真实章节：**第 5 章化学（5.1–5.65）/ 第 6 章粉尘（6.1–6.9）/ 第 7 章物理（7.1–7.8）/ 第 8 章生物（8.1–8.5）/ 第 9 章特殊作业（9.1–9.10）**。第 5–7 章（82 因素）明细已核对；第 8–9 章（15 因素）仅身份核对、明细 pending。
- 周期：38 因素单值；22 因素分档 → `period.status=input_required`；22 因素无在岗期间检查（`kind=none`）；15 因素 pending。
- **编排层公开函数组**（M5-1 上收后）：`build_context / build_position / build_record / resolve_ruleset_for / compute_plan / compute_coverage / run_scan / scan_with_reconcile / compare / compare_rounds_model / build_report_model / generate_report / report_from_inputs / selfcheck_payload / parameter_overview / gate_overview / policy_thresholds`——CLI 与 GUI 都只准经它取数。
- **GUI 分层**：`gui/service.py`（唯一引擎 import）→ `gui/main_window.py`（六页签装配 + `OHSCHECK_GUI_SMOKE=1` 自动退出通道）→ `gui/pages/`（表现层，AST 三守门）；冻结态入口薄封装 `gui_entry.py` / `cli_entry.py`（`multiprocessing.freeze_support()`）。
- **基准层事实**：门槛全走 `BenchEnv.threshold()`（缺键 exit 2）；`max_runtime_seconds` 已被执行；空分母 → `not_enabled` + exit 1；runner 套件函数内延迟 import（探活打桩可达）。
- **失败件原因码全 8 个**：`read_error/bad_json/schema_invalid/unknown_factor/unknown_exam_type/container_too_large/gate_blocked/missing_input`。
- 真值件编号：001–024 算例，025–072 批量件。

---

## 二、M6 待办（按序）

> M6 目标（`plan/05` §四）：**脱敏发布与收尾**——脱敏四步 + 干净环境验证 + **CI 首推全绿**（本项目第一次真实 CI）+ tag/Release + 附件可复跑 + README 转正 + 缓议项清零。

### 2.1 M6-1 脱敏四步 + 产物本体扫描

- 脱敏四步 + 命令与结论留档 `plan/RELEASE-M6.md`（DoD 判据）；
- 产物本体扫描（exe/zip 内不含敏感路径、真实姓名、本机盘符等）。

### 2.2 M6-2 干净环境验证

- `git archive` 导出树 + 全新 venv，按 README 逐条跑通；**同一 extras 集合下**收集数一致。

### 2.3 M6-3 CI 首推（第一次真实 CI，预算多轮诊断）

- **对外动作（接远端、push）需用户确认一次**（M6-4 同）；
- 四矩阵（ubuntu/windows × 3.8/3.12）全绿；注意 plan/03 §十一：Linux job 需补 `libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1`（Qt offscreen 依赖）。

### 2.4 M6-4…M6-7 Release 链

| # | 任务 | 判据 |
|---|---|---|
| 1 | `git tag -a vX.Y.Z` + `gh release create`（**对外动作需用户确认一次**） | Release 附 ASCII 名 zip |
| 2 | Release 附件固定时间戳可复跑 + sha256 留档 | — |
| 3 | 真下载附件 → sha256 对账 → 中立目录解压跑 `--selftest` 通过 | M5 已验证的验收路径复用 |
| 4 | 产物与发布源码同基线：`git diff <构建提交>..HEAD -- src/ tools/*.spec` 为空 | — |

### 2.5 M6-8/M6-9 收尾

- README 状态行转正 + CI 徽章 + 路线图最后一棒打勾；
- 缓议项清零（`plan/06` §三 H-1/H-2/H-3/H-4/H-5 逐项给"做/跳过"显式决策，含理由）；H-6 已裁决（D-76）。

### 2.6 M6 收尾

- 回写 `plan/00` 状态表、`plan/05` M6 DoD 逐项证据、`plan/06` 决策记录（M6 新发现）；
- 提交（正常开发流）；**push/tag/release 前须用户确认**。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全量口径速查见 `plan/HANDOFF-M5.md` §三（历史快照）或 `plan/06`。本节只列与 M6 直接相关的。

| 口径 | 内容 | 落点 |
|---|---|---|
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |
| **对外动作需确认** | 接远端 / push / tag / `gh release create` 均须用户显式确认 | M6-3/M6-4 |
| **打包固定 3.12 通道** | PyInstaller ≥6 打 GUI（5.x 确定性崩）；发布构建用 3.12 | D-14 |
| **datas 白名单单一事实源** | `packaging.DATA_WHITELIST` → `gen_spec.py` 生成 spec（禁手改）；改数据走 `tools/gen_*.py` 再重打包 | D-77 |
| **不得手改 dist 内冻结产物** | 数据改动 → `tools/gen_*.py` → 重新打包 | HANDOFF-M5 §七 |
| **XLSX 自写最小 OOXML writer** | 否决 openpyxl（D-06）；README 台账已按实态修正（M5） | 报告层 |
| **品牌隔离** | 公开文档不提姊妹项目业务领域 | 00 决策记录 |
| **演示/真值零真实信息** | 虚构姓名代号 + 测试号段 | plan/01 §四 |
| **CI 编码守卫** | 所有会打印的入口走 `_ensure_utf8_stdio()` 探针式 reconfigure | D-39 |
| **CI checkout `fetch-depth: 0`** | 历史脱敏扫描依赖全量历史；守门测试断言 | plan/03 §十一 |

---

## 四、本机环境坑（**只写实测过的**；全量见 `plan/HANDOFF-M5.md` §四）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **heredoc 里的非 ASCII** | `py -3.8 - <<'PY'` 内联中文补丁偶发编码报错 | 长中文补丁走**临时 .py 文件**（仓库树外），首行 `# -*- coding: utf-8 -*-`，跑完即删 |
| **Git Bash `/tmp` 与 Windows Python 不通** | heredoc 里写 `/tmp/x` → FileNotFoundError | 临时目录用仓库树外 Windows 路径 |
| **`py -0p` 两条通道** | 3.8.8 与 3.12 并存 | 双通道各跑测试；**打包/发布构建固定 3.12**（D-14） |
| **spec 路径以 spec 所在目录为基准** | 首版仓库根相对路径 → "tools\src\... not found"（K-1） | `gen_spec.py` 模板用 `SPECPATH` 拼绝对路径；spec 禁手改 |
| **3.8 零依赖守门是显式 stdlib 白名单** | 新增 stdlib import（如 `multiprocessing`）→ 3.8 通道守门红（K-2） | 新增 stdlib import 须同步补 3.8 白名单（tests/test_scaffold.py） |
| **offscreen Qt 三坑** | 无字体数据库（中文方框）/ `QFileDialog` 模态阻塞 / QImageWriter 不支持 GIF（K-3） | 显式加载系统中文字体文件 / 演示动作绕开"浏览…"按钮 / Pillow 固定参数编码 |
| **json.dumps 不能直接序列化 Decimal** | 载入 `parse_float=Decimal` 后改数据写回会 TypeError | 测试用 `ohscheck.loaders.dumps_stable`（注意它会把它数值小数写成 JSON 字符串） |
| **测试 monkeypatch 引擎函数** | runner 套件函数内延迟 import，运行期打桩可达 | 探活/注入类测试用完即还原（try/finally） |

**M0–M5 期未验证的**（M6 才会触到，别当已验证）：CI 真跑（无远端）、`git archive` 干净树验证、`gh release` 链路、产物本体扫描、Release 附件下载回验。

---

## 五、M6 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M6** 表（M6-1 … M6-9）。逐项要求：

- [ ] M6-1 脱敏四步 + 产物本体扫描，命令与结论留档 `plan/RELEASE-M6.md`
- [ ] M6-2 干净环境验证（`git archive` 导出树 + 全新 venv，按 README 逐条跑通）；同一 extras 集合下收集数一致
- [ ] M6-3 CI **首推**四矩阵全绿（第一次真实 CI，预算多轮诊断；**对外动作需用户确认一次**）
- [ ] M6-4 `git tag -a vX.Y.Z` + `gh release create`（**对外动作需用户确认一次**）
- [ ] M6-5 Release 附件 ASCII 名 zip + 固定时间戳可复跑 + sha256 留档
- [ ] M6-6 真下载附件 → sha256 对账 → 中立目录解压跑 `--selftest` 通过
- [ ] M6-7 产物与发布源码同基线（`git diff <构建提交>..HEAD -- src/ tools/*.spec` 为空）
- [ ] M6-8 README 状态行转正 + CI 徽章 + 路线图最后一棒打勾
- [ ] M6-9 缓议项清零（含显式"跳过"决策；H-6 已裁决 D-76）

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8  -X utf8 -m pytest -q                      # 双通道各跑一遍（M5 基线 227 项）
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK（含 clauses.json）
py -3.8  -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8  -X utf8 tools/gen_synthetic.py --check    # FROZEN_TRUTH_OK（74 文件）
py -3.8  -X utf8 tools/check_literals.py --selftest
py -3.8  -X utf8 tools/check_literals.py
py -3.8  -X utf8 tools/gen_spec.py --check         # M5 新增：spec 与白名单一致
py -3.8  -X utf8 -m ohscheck selfcheck
py -3.8  -X utf8 -m ohscheck bench
```

**M6 收尾注意**：GUI 层 AST 三守门与字面量门禁不得放松；打包后**冻结态产物**由 spec 的 datas 白名单决定；发布 zip 内不得出现 `plan/` 之外的本地路径泄漏（脱敏扫描把关）。

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
py -3.12 -X utf8 tools/gen_spec.py --check       # spec 与 datas 白名单一致

# CLI
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck plan <岗位画像.json>
py -3.8 -X utf8 -m ohscheck check <档案.json>
py -3.8 -X utf8 -m ohscheck scan <档案目录> --baseline <上一轮目录> --out <报告目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck compare
py -3.8 -X utf8 -m ohscheck report <输出目录> --position <岗位.json> --directory <档案目录> --baseline <上一轮目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck bench [--only matrix|coverage|compare|false_positive]
py -3.8 -X utf8 -m ohscheck version

# GUI / 打包（3.12 通道）
py -3.12 -X utf8 -m ohscheck gui                 # 桌面界面（缺依赖 → exit 3；OHSCHECK_GUI_SMOKE=1 offscreen 自动退出）
py -3.12 -X utf8 tools/gen_demo_assets.py        # 演示素材（--check 两次生成 sha256 一致）
py -3.12 -m PyInstaller tools/packaging.spec --noconfirm --distpath build-m5/dist --workpath build-m5/work
build-m5/dist/ohscheck/ohscheck-cli.exe selftest <out.json>    # 冻结态自检（frozen/inside/ok 三断言）

# 测试
py -3.8  -X utf8 -m pytest -q                       # M5 基线：227 项
py -3.12 -X utf8 -m pytest -q
py -3.8  -X utf8 -m pytest -q tests/test_m5.py      # M5 验收门（三守门 + 三方对账 + exit 3 回归 + spec 守门）

# M6 新增（发布期逐步充实）
git archive --format=zip -o /<外部路径>/src.zip HEAD    # 干净树导出（M6-2）
gh release create vX.Y.Z dist-zip/*.zip                 # 对外动作：先经用户确认
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标（含"未启用"） · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失·溯源断言不满足（拒导） · `3` 缺可选依赖（GUI）。

**M6 调试常用真值件**（同 M3/M4/M5）：

| 因素 | 代码 | 周期 |
|---|---|---|
| 苯 | `GBZ188-5.19` | 12 个月（单值） |
| 铅及其无机化合物 | `GBZ188-5.1` | 分档（`input_required`） |
| 噪声 | `GBZ188-7.1` | 分档（`input_required`） |
| 四乙基铅 | `GBZ188-5.2` | 无在岗期间检查（`kind=none`） |
| 布鲁氏菌（明细 pending） | `GBZ188-8.1` | 门控会拦 |

**报告产物字节可复现**：`scan`/`report` 必须注入 `--generated-at`；`evidence.json` 本身不写时间。
**溯源硬断言**：报告导出前自动执行，不满足抛 `TraceAssertionError`（exit 2），不留半成品（D-64）。
**基准探活**：改基准输入文件做实验须用临时目录 copytree，**不得动 `data/benchmark/`**。

---

## 七、禁止事项

- **不得手改** `data/rules/`、`data/benchmark/`、`data/truth/`、`data/knowledge/clauses.json` 下任何产物（唯一写入者是 `tools/gen_*.py`）；`tools/packaging.spec` 同理（唯一写入者 `tools/gen_spec.py`）。
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
- **未经用户显式确认，不得**接远端 / push / tag / `gh release create`（对外动作，M6-3/M6-4）。
