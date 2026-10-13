# HANDOFF-M1：数据先行（下一棒续接快照）

> **状态**：M0 已完结（2026-10-14），本文件是 M1 的续接快照。**新对话从本文件开始，不依赖对话记忆。**
> 用法：新对话输入 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`
> （本文件内一律用相对路径 `plan/HANDOFF-M1.md`，避免入库本机盘符路径）

---

## 一、当前进度（M0 完结实态）

**交付物**：可运行的**骨架**已就位——规则加载 + status 门控 + 版本锚定 + 矩阵/覆盖度/周期判定 + 批量扫描 + 跨轮对账 + 报告导出（MD/XLSX/证据链）+ CLI 八子命令 + 基准四套件 + 126 项测试 + CI workflow。

| 项 | 实态 |
|---|---|
| 版本 | `ohscheck 0.1.0`（`src/ohscheck/__init__.py`） |
| 测试 | **126 项**，Python **3.8.8** 与 **3.12** 双通道全绿（0 failed/0 skipped） |
| 基准 | `ohscheck bench` 四套件全达标退出 0：matrix 5/5、coverage 10/10、compare 3/3、false_positive 误报 0 |
| 规则包 | `data/rules/`（3 文件）**全部条目 pending**（M0 初态）；`--check` 再生成逐字节一致 |
| 合成夹具 | `data/benchmark/`（5 文件）带植入真值；`--check` 再生成逐字节一致 |
| CI | `.github/workflows/ci.yml` 就位（4 矩阵 + `fetch-depth: 0`）——**未接远端，一次都没跑过** |
| 远端 | **无远端**。本机 git 仅本地提交，未 push |

**M0 完成证据**：`plan/05-数据计划与里程碑.md` §四 M0 DoD 表（15/15 逐项证据 + 6 条实测发现 F-1–F-6）。

**数据侧实态（关键）**：
- `data/rules/ruleset-2025.json` / `ruleset-2014.json`：**32 个危害因素坐标骨架**（第 5 章 24 节 + 第 6 章 8 节），原因因素名称/项目/周期**一律为占位或 null**，`status=pending`。
- `data/knowledge/`：**尚未建**（M1 任务）。
- `data/truth/`：**尚未建**（M1 任务）。
- M0 期已获取的官方材料（**尚未入库为快照**）：GBZ 188—2025 全文 PDF，gov.cn 附件 `https://www.gov.cn/zhengce/zhengceku/202509/P020250906581488346891.pdf`，1,553,783 字节 / 139 页，`pdftotext -enc UTF-8 -layout` 解析 75,555 汉字零丢失。

---

## 二、M1 待办（按序）

### 2.1 材料入库（先做，阻塞其余）

| # | 任务 | 判据 | 备注 |
|---|---|---|---|
| 1 | 抓取 GBZ 188—2025 全文 PDF 落 `data/knowledge/raw/` | 文件 sha256 登记入 `data/README.md` | **必须**在 `.gitattributes` 给 `data/knowledge/raw/**` 标 `-text`（冻结快照禁归一化，否则克隆后 sha256 失配） |
| 2 | 解析 PDF → 文本快照入 `data/knowledge/raw/` | 汉字数 ≥ 75,555（不丢字） | 用 `pdftotext -enc UTF-8 -layout`；解析后的 stat 写入台账 |
| 3 | 建 `data/knowledge/clauses.json`（依据索引） | 每条挂 标准号 + 节号 + URL + 抓取日期 + sha256 | 现行代码的 `parameter_overview` 已能从规则包 basis 输出出处，clauses 是更细一层的索引 |
| 4 | 处置 4 个**待核对项**（`plan/06` §二 P-1–P-4） | 逐条核对或显式留 `pending` + 记录已查渠道 | **未核对不得写入规则包 basis**；两渠道都查不到 → 继续推进不停摆 |

### 2.2 规则逐条核对与填充（M1 主战场）

按 `plan/05` §1.3 的核对清单 **C1–C8** 逐条做：

| 判据项 | 内容 |
|---|---|
| C1 | 5.x/6.x 节次标题 → `factor_id`/`factor_code`/`factor_name`/`chapter`/`category` |
| C2 | 各节"目标疾病"（记录名称，不参与判定） |
| C3 | 各节"检查内容"**必检项**（拆分粒度：一个检验项一行） |
| C4 | 各节"检查内容"**补充项** → `supplementary_items` |
| C5 | 选检项目：2025 版上岗前/在岗期间/离岗时 `optional_items == []`（由 `optional_items_policy: emergency_only` **数据**保证，已实现） |
| C6 | 各节"检查周期" → `period.value`（整数月）+ basis |
| C7 | 适用性阈值：原文有阈值 → `kind=threshold`；表述"根据具体情况" → `kind=input_required` |
| C8 | 2025 版前言"主要技术变化"逐条 → 供 `compare` 通道做期望差异 |

**代码入口已备好**：改 `tools/gen_rulesets.py` 的 `_pending_factor()` / `CHAPTER_PLAN` 为逐条填充，然后 `py -3.8 tools/gen_rulesets.py` 整目录重生成（**产物禁手改**）。

### 2.3 合成监护档案与真值库

| # | 任务 | 判据 |
|---|---|---|
| 1 | 写 `tools/gen_synthetic.py`（自研 **splitmix64**，禁 stdlib `random`/禁 set 迭代序/禁系统时钟） | 固定 seed 可复现；`--check` 位级一致 |
| 2 | 产出 `data/truth/`：`plan/05` §2.3 算例矩阵**全覆盖** | 化学（苯/铅）、物理（噪声/高温）各设算例 |
| 3 | 植入真值语义按 `plan/05` §2.4 | `expect` 主期望 + `also_expect`；判据：**全部非 pass 集合**对账 |
| 4 | 误报对照集显式声明 | `should_be_clean: true`（干净档）/ 应降级档（别名可映射 → 只报 warning） |
| 5 | `data/README.md` 台账登记全部产物 sha256 | 含 `_private/` 不给入仓的说明 |

### 2.4 过渡期口径登记

按 `plan/05` §三 **T1–T7** 逐条核对并在 `data/README.md` 留档。T3/T4/T5 是"动了会打挂基准"的口径，**已在新代码中实现并锁测试**，M1 只需登记不改动。

### 2.5 门控在真实数据上验证（M1-7）

M0 期门控只在合成夹具上验证。M1 需验证**真实规则包**上的作用域行为：
- 部分因素已核对（`verified`）、部分未核对（`pending`）→ `plan`/`check` 只拦**引用到的** pending 条目；
- `compare`/`bench` 在项目明细 pending 时**仍放行**（结构对照/机制验证不依赖明细）。

### 2.6 M1 收尾

- 回写 `plan/00` 状态表、`plan/05` M1 DoD 逐项证据、`plan/06` 待核对项状态；
- 写 `plan/HANDOFF-M2.md`（六段式）；
- 提交（正常开发流）。

---

## 三、既定口径清单（动了会打挂基准 / 测试，改前必对照）

> 全部落在 `plan/06-决策记录.md` 与 `plan/03`/`plan/04`。此处是**动手前的速查**。

| 口径 | 内容 | 落点 |
|---|---|---|
| **版本锚定键 = 体检日期** | `exam_date`（不是编制年度、不是"年度"） | `rules/version.py`；决策 D-10 |
| **年度含切口日即报错** | 只给年度且含切口日 → `AmbiguousYearError` → exit 2，**宁报错不猜** | `rules/version.py`；D-11 |
| **门控按计算路径分作用域** | `plan`/`check` 走 full 深度；`compare`/`bench` 走 minimal；**只拦本次引用到的条目** | `rules/gate.py`；D-12 |
| **第三态 `input_required`** | 放行门控但运行时**必索**，缺失即 exit 2，**绝不静默取默认值** | `rules/gate.py` + `pipeline`；D-13 |
| **应检项集 = 仅必检项** | `expected = required_items`；补充/选检项**不进判定**（缺失不报）→ **工具不做"补充检查合规"判定** | `engine/matrix.py`；D-16 |
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
| **选检项目口径是数据** | `optional_items_policy: any \| emergency_only`，**不在代码里按版本号硬编码** | `rules/schema.py`；D-46（新增） |
| **DoD 诚实性** | 未接远端期间一律写"本地等价校验"，**未推送 = 未跑 CI** | D-41 |

---

## 四、本机环境坑（**只写实测过的**）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| **Git Bash `/tmp` 与 Windows Python 不通** | `py -3.8 - <<PY` 里写 `/tmp/x/records/...` → `FileNotFoundError` | 临时目录用**仓库树外的 Windows 路径**（如 `D:/.../\_e2e_scratch`），用完即删 |
| **`py -0p` 有两条通道** | 3.8.8 与 3.12 都装着 → 双通道各跑一遍 | 本项目两者都能跑；M5 打包固定用 **3.12**（PyInstaller ≥6，见 D-14） |
| **中文控制台编码** | 本机一律 `py -3.8 -X utf8` 跑命令 | 但 `-X utf8` 会**整体掩盖**代码里的非 ASCII 输出缺口 → 故入口都装 `_ensure_utf8_stdio()`，并有 cp1252 复现测试 |
| **`json.dumps` 不能直接序列化 Decimal** | 载入用了 `parse_float=Decimal`，测试里改数据后写回会 `TypeError` | 测试一律用 `ohscheck.loaders.dumps_stable` |
| **零字面量门禁会扫中文注释** | 文档里写"2026 年"也会被扫 | 口径已写死：中文说明性散文豁免；代码语法里的年份报错（D-27）；`period.py`/`version.py` 的日期示例已改中文叙述 |
| **pyc 偶发损坏** | 未见（M0 期未出现） | 出怪错先清 `__pycache__` 再跑；单轮崩溃直接重试 |

**M0 期未验证的**（M5 才会触到，别当已验证）：PyInstaller 打包、PySide6 offscreen、冻结态 `--selftest` 真跑、中立目录验收。

---

## 五、M1 DoD（逐项 checklist，收尾逐项打勾）

见 `plan/05-数据计划与里程碑.md` §四 **M1** 表（M1-1 … M1-7）。逐项要求：

- [ ] M1-1 GBZ 188—2025 PDF 快照入 `data/knowledge/raw/` + sha256 台账 + `.gitattributes` 标 `-text`
- [ ] M1-2 第 5/6 章主要危害因素逐条转写 + 原文核对（C1–C7），`verified` 条目数 > 0
- [ ] M1-3 2014 版差异导向骨架入库（前言引述的差异条目），未引述部分保持 `pending`
- [ ] M1-4 合成监护档案 + 植入真值库（算例全覆盖）+ `--check` 位级一致
- [ ] M1-5 误报对照集（应零命中 / 应降级）显式声明
- [ ] M1-6 `data/README.md` 台账登记全部产物 sha256；待核对项清单更新
- [ ] M1-7 门控作用域在真实数据上验证（`plan`/`check` 只拦引用到的 pending）

**收尾必跑**（每次里程碑收尾的固定动作）：

```
py -3.8 -X utf8 -m pytest -q                      # 双通道名都跑
py -3.12 -X utf8 -m pytest -q
py -3.8 -X utf8 tools/gen_rulesets.py --check     # FROZEN_RULESETS_OK
py -3.8 -X utf8 tools/gen_cases.py --check        # FROZEN_CASES_OK
py -3.8 -X utf8 tools/gen_synthetic.py --check    # M1 新增
py -3.8 -X utf8 tools/check_literals.py --selftest
py -3.8 -X utf8 tools/check_literals.py
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck bench
```

**M1 收尾注意**：规则包填充 verified 条目后，`bench` 的生产包门槛会真正生效；此时 `data/benchmark/`（合成夹具）**不受影响**——基准验机制、不验国标内容，两套数据**刻意分离**，不要合并。

---

## 六、关键命令速查

```bash
# 环境（Git Bash）
export PYTHONPATH=src                       # 未 pip install -e 时用；建议直接 pip install -e ".[dev]"

# 生成冻结产物（唯一写入者；产物禁手改）
py -3.8 -X utf8 tools/gen_rulesets.py            # → data/rules/（M0 全 pending）
py -3.8 -X utf8 tools/gen_cases.py               # → data/benchmark/（合成夹具 + 真值）
py -3.8 -X utf8 tools/gen_rulesets.py --check    # 再生成逐字节一致守门
py -3.8 -X utf8 tools/gen_cases.py --check

# 门禁
py -3.8 -X utf8 tools/check_literals.py --selftest   # 阳性对照（必先跑）
py -3.8 -X utf8 tools/check_literals.py              # 扫描（0 命中 = exit 0）

# CLI
py -3.8 -X utf8 -m ohscheck selfcheck
py -3.8 -X utf8 -m ohscheck plan <岗位画像.json>
py -3.8 -X utf8 -m ohscheck check <档案.json>
py -3.8 -X utf8 -m ohscheck scan <档案目录> --out <报告目录>
py -3.8 -X utf8 -m ohscheck compare
py -3.8 -X utf8 -m ohscheck report <输出目录> --position <岗位.json> --directory <档案目录> --generated-at 2026-10-14T00:00:00
py -3.8 -X utf8 -m ohscheck bench [--only matrix|coverage|compare|false_positive]
py -3.8 -X utf8 -m ohscheck version

# 测试
py -3.8  -X utf8 -m pytest -q
py -3.12 -X utf8 -m pytest -q
```

**退出码速查**：`0` 无不符合 / 基准达标 · `1` 检出不符合 / 基准未达标 · `2` 用法·输入·门控·待输入·年度歧义·门槛缺失 · `3` 缺可选依赖（GUI）。

**报告产物字节可复现的用法**：`report` 必须注入 `--generated-at`（否则报告头时间随运行变，破坏同输入同字节）；`evidence.json` 本身**不写时间**。

---

## 七、禁止事项

- **不得手改** `data/rules/` 与 `data/benchmark/` 下任何产物（唯一写入者是 `tools/gen_*.py`）。
- **不得**把 `pending` 条目放进核查路径（门控会拦，别绕过）。
- **不得**在演示/基准里引入任何真实劳动者信息（虚构姓名代号 + 测试号段）。
- **不得**在公开文档提及姊妹项目业务领域（品牌隔离）。
- **不得**为迁就引擎而改真值；分两种情形（`plan/05` §2.4）：检查器谓词不自洽 → 只改谓词；口径本身定错 → 引擎与真值**同源修正**，统一验收门 = `gen_cases.py --check` 通过。
