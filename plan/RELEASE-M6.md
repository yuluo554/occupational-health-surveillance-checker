# RELEASE-M6：脱敏发布留档（M6-1 DoD）

> 基准日：2026-10-14。本项目首次对外发布前的脱敏扫描记录：命令与结论逐条留档，可复跑。
> 工具：`tools/audit_sensitive.py`（M6-1 实装，四步扫描 + 阳性对照；plan/03 §三 预留位落地）。
>
> **本文件自身不带任何本机标识词面**（L-3 教训：留档若写明文 token，会随提交进入
> git 历史——发布源码 zip 含 `plan/`，等于发布泄漏件）。token 清单由扫描器在
> 运行时从本机环境实算（git 身份邮箱、`getpass.getuser()`、仓库绝对路径段、用户
> 主目录模式），本文件只记录**类别与实算来源**，词面值见扫描器每次运行的首行输出。

---

## 一、脱敏四步定义与命令

| 步 | 扫描面 | 通过判据 | 命令 |
|---|---|---|---|
| step1 tree | 工作树全部**已跟踪文件**（`git ls-files -z`；**无目录级豁免**，`plan/` 逐文件扫描，迭代 D-1） | 0 命中 | `py -3.12 -X utf8 tools/audit_sensitive.py` |
| step2 history | git **全量历史**逐提交 grep（`fetch-depth: 0` 保证不空转，D-40；提交数 0 = 空转失败；**无目录级豁免**） | 0 命中 | 同上（单步：`--only history`） |
| step3 dist | **产物本体**二进制扫描（构建目录逐文件字节级） | 本项目自有产物 0 命中；第三方官方路径豁免逐条显式列出 | 同上（单步：`--only dist --dist-dir <目录>`） |
| step4 meta | git 作者/提交者身份清单 | informational（恒通过）——发布身份取舍属对外动作，由发布者显式决策 | 同上（单步：`--only meta`） |

阳性对照（任何"0 命中"结论必须先跑，D-27 同族）：

```bash
py -3.12 -X utf8 tools/audit_sensitive.py --selftest
# → AUDIT_SELFTEST_OK: 文本 token 全报出（machine_path,username,users_home），
#   干净对照 0 命中，二进制官方路径豁免 0 误报、盘符根泄漏报出 1 处，
#   plan/ 路径阳性对照报出 3 处，中性占位豁免 0 命中且真实路径仍报出
```

双通道验证：3.8 与 3.12 均跑过 selftest + 全量四步，结论一致。

## 二、禁用 token 类别（运行时实算，来源见扫描器 `collect_tokens`）

| 类别 | 实算来源 | 说明 |
|---|---|---|
| `identity_number` | git 全部作者/提交者**邮箱**中的 ≥6 位纯数字串 | QQ 号形态；实测从历史邮箱实算出 1 个 |
| `username` | `getpass.getuser()`，词边界匹配 | 词边界避免误伤包含它的厂商串（ASUSTek） |
| `machine_path` | 仓库根绝对路径的上级目录段（排除常规系统目录与仓库目录名本身） | 仓库目录名与日期标签是**有意公开**的项目坐标（plan/00 命名约定），不收 |
| 盘符 needle（二进制） | 仓库所在盘符 + `\` | 仅二进制扫描用 |
| `users_home` | `<仓库盘>[/\\]Users[/\\]` 模式 | 通用 Windows 用户目录泄漏形态 |

## 三、实测结论（2026-10-14，历史重写后终态）

```
token 实算：identity_numbers=[1 个 QQ 形态号]、username=[本机用户名]、
            repo_path_segments=[盘符, 工程段名]、users_home_pattern=[盘符]
step1 tree     : 扫描 176 份已跟踪文件（plan/ 豁免），命中 0
step2 history  : 全量历史 13 个提交逐提交扫描，命中 0
step3 dist     : 扫描 244 个产物文件，第三方官方路径豁免 64 处，本项目产物命中 0
step4 meta     : git 身份清单（informational）：
    yuluo554 <yuluo554@users.noreply.github.com> | committer: yuluo554 <yuluo554@users.noreply.github.com>
→ exit 0
```

> 上表是 M6 期（整目录豁免口径）的历史快照，保留原值；**新口径复测见 §六.1**。

### 3.1 实测发现与处置（M6 期 L 系列）

| # | 发现 | 处置 |
|---|---|---|
| **L-1** | **干净 venv 直接红**：`tests/test_scaffold.py` 三个 CI 守门测试 `import yaml`，注释写"缺失则跳过"却**没有 skip 逻辑**——主环境恰好装了 PyYAML 掩盖缺失；CI `.[dev]` 里没有 PyYAML，首推必挂 | PyYAML 显式进 `dev` extras（pyproject 注明缘由）；测试注释如实改写 |
| **L-2** | **无 PySide6 环境 exit-3 测试红**：`test_gui_import_error_during_call_still_exits_3` 的前提是 `import ohscheck.gui.main_window` 成功（"import 成功但调用阶段才缺依赖"），干净 venv 连 import 都过不去 | 补 `pytest.importorskip("PySide6")`；该环境由同文件打桩 `__import__` 的测试覆盖同一 exit 3 路径 |
| **L-3** | **扫描器自噬**：第一版扫描器把本机标识**硬编码**进自己源码（token 正则、selftest 合成串、注释），提交后历史即带词面——"扫描器本身是泄漏源"。同轮还发现留档（本文件首版）也写了 token 明文 | **token 全部改运行时实算**（来源见 §二）；扫描器源码与留档零词面；两个未推送的污染提交（M6-1 首版、L-2 修复）软重置后重写为单一干净提交 |

### 3.2 step3 第三方官方路径豁免清单（64 处，逐条实测字节上下文后显式豁免）

| 嵌入串 | 出处 | 文件 | 性质 |
|---|---|---|---|
| `C:\Users\qt\work\...`（Qt/PySide 官方构建机 PDB 路径） | Qt/PySide 官方构建 | `Qt6*.dll`、`shiboken6.abi3.dll`、各 `plugins/*.dll` | 供应商调试串，非本机信息 |
| `D:\a\1\b\bin\amd64\*.pdb`（python.org 官方 CI，Azure DevOps agent 盘） | python.org 官方构建 | `python312.dll`、`python3.dll`、14 个 `*.pyd` | 供应商调试串 |
| `D:\a\_work\1\s\...`（微软 MSVC 官方 CRT 构建路径） | 微软官方构建 | `vcruntime140*.dll`、`msvcp140*.dll`（含 PySide6/shiboken6 目录下副本） | 供应商调试串 |
| `D:\git-sdk-64-full\...`（Git for Windows 官方构建） | GfW 官方构建 | `libcrypto-3-x64.dll`、`libssl-3-x64.dll` | 供应商调试串 |
| `ASUSTek COMPUTER INC`（USB 厂商串）、`Caucasus Standard Time`（时区名） | Qt6Gui/Qt6Core 字符串表 | `Qt6Gui.dll`、`Qt6Core.dll` | 与用户名同词面时的误报排除 |

**核实方法**：全部命中逐一提取字节上下文（RSDS PDB 锚点 + NUL 截断取完整路径，或字符串表上下文），确认前缀属于上表官方目录/厂商串才豁免；豁免逻辑写死在 `tools/audit_sensitive.py`（`_OFFICIAL_PDB_DIRS` + `_binary_exempt`），非人工过目后放行。

**本项目自有产物（双 exe / 全部 pyc / `_internal/data`）对全部实算 token 零命中。**

## 四、数据面核查（脱敏纪律的既定要求，plan/01 §四）

| 项 | 结论 | 证据 |
|---|---|---|
| 真值库人员姓名 | 全部虚构代号（`示例人员 A-001…` / `示例人员 SYN-X-NNN`），72 档案逐一核对 | `grep -h employee_name data/truth/records/*.json \| sort -u` 仅虚构代号 |
| 人员编号 | 全部 `SYN` 后缀测试号段（`90000000001SYN` 形态），无真实身份证号格式 | 正则扫描 18 位身份证号格式 0 命中 |
| 基准/演示数据 | 合成规则集 `SYNTHETIC-` 前缀，非真实标准 | `data/README.md`、`data/benchmark/` |
| 姊妹项目 | 公开文档零提及（品牌隔离，D-43）；"姊妹项目"字样仅出现在纪律条款自身 | step1 扫描 + 人工复核 |
| `data/truth/_private/` | 不存在（本机也未创建），gitignore 已排除 | `.gitignore` |

## 五、发布身份决策（step4 informational → 显式决策）

git 历史存在两种作者身份：`yuluo554 <yuluo554@users.noreply.github.com>`（发布身份）与一个**早期个人邮箱**（多数提交）。该个人邮箱与"用户目录路径"同属**个人标识**，与 `plan/` 内本机路径泄漏一并处理。

- **统一为发布身份**：个人邮箱既存在于提交**元数据**，也出现在本文档正文（原 step4 回显行与本节引述行）——故按"素材真实性/脱敏"纪律**统一改写**为 `yuluo554 <yuluo554@users.noreply.github.com>`，并同步重建 tag（annotated tag 的 tagger 身份）。
- **回填失效声明**：改写历史会使改写前的 sha256 留档与"同基线"尾注指向旧提交号；M6-7 的"产物与发布源码同基线"以**内容**一致为准（`git archive` 树比对），提交号变更不影响内容基线，故留档以内容为准并在此声明。
- **后续纪律**：此后提交一律使用 `yuluo554@users.noreply.github.com`（GitHub 私有邮箱保护）。

## 六、plan/ 豁免口径说明

HANDOFF 快照（`plan/HANDOFF-M1…M6.md`）含本机路径**示例**（"临时目录用仓库树外的 Windows 路径"句式）。这些是写给续接者的环境坑记录，属计划文档；HANDOFF-M6 §五 的发布判据是"发布 zip 内不得出现 **`plan/` 之外**的本地路径泄漏"。

- **修正（2026-10-14）**：原口径对 `plan/` **整目录豁免**，导致 `plan/HANDOFF-M4/M5.md` 里的**本机工作根路径**（工作盘符 + 工作目录名 + 仓库树）漏检——`plan/` 本身是**入仓公开**内容，豁免它等于把泄漏面放在扫描盲区。现口径改为：`plan/` 内**个人标识**（本机路径/个人邮箱/用户名）**一律扫描**，仅对"环境坑示例中的中性占位"放行；`plan/` 内已改为 `<workdir>` 占位符。
- **代码收口（2026-10-19，迭代 D-1）**：上述"现口径"此前只写在本节，代码仍留 `PLAN_EXCLUDE = "plan/"` 整目录跳过——留档与实现相反。本次删除该常量与 `step1_tree`/`step2_history` 两处前缀跳过，改为**逐文件 / 逐提交 blob** 扫描；中性占位豁免收窄为**仅命中点落在占位式路径内**（角括号 `<workdir>`、带 `...` 省略段的示例路径），不做任何目录级/行级豁免。`--selftest` 增加 plan/ 阳性对照（合成 `plan/x.md` 含本机标识必须报出）+ "占位放行 / 真实路径报出"对照。CI 常驻该门禁（`--selftest` + 全跑）。
- **顺带修掉一处静默漏读（2026-10-19，迭代 D-1 实测）**：`git ls-files` 默认对非 ASCII 路径做引号转义（`"plan/00-README\346..."`），旧代码按该引号串打开**必然失败**却被计入"已扫描"——实测 8 份（`plan/00–06` 七份 + `docs/技术报告.md`）从未被读入。改用 `git ls-files -z`，并把"无法读取"单列为阻塞项（非 0 不得视为通过）。

### §六.1 新口径实测（2026-10-19，py3.12）

```
step1 tree     : 扫描 184 份已跟踪文件（无目录级豁免，plan/ 逐文件），命中 0
step2 history  : 全量历史 18 个提交逐提交扫描，命中 0
step3 dist     : 扫描 244 个产物文件，第三方官方路径豁免 64 处，本项目产物命中 0
→ exit 0
```

- `plan/` 14 份入仓文件**全部进入扫描范围**（旧口径只扫 177 份且其中 8 份读不出）；逐文件扫描 `plan/` 命中 **0**，故无需先修 `plan/` 内容。
- selftest：`AUDIT_SELFTEST_OK: … plan/ 路径阳性对照报出 3 处，中性占位豁免 0 命中且真实路径仍报出`。

发布源码 zip（M6-5）含 `plan/` 时按本节口径接受；dist 产物 zip 不含 `plan/`，不受影响。

## 七、M6-2 干净环境验证（2026-10-14）

`git archive --format=zip HEAD` 导出干净树（仓库树外解包）+ 全新 venv（3.8.8），按 README 逐条跑通：

| 步骤 | 命令 | 结果 |
|---|---|---|
| 安装 | `pip install -e ".[dev]"` → `".[gui]"` | 成功；PySide6 3.8 上限实装 6.6.3.1 |
| 测试 | `pytest` | **223 passed, 4 skipped**（skip 全部为 PySide6 相关 importorskip + 打桩测试，与 CI 4 矩阵的 3.8 无 gui 通道口径一致） |
| CLI | `selfcheck` / `bench` / `compare` / `check` / `scan` / `report` | 全链路退出码符合速查表（check 008 与 scan exit 1 = 真实缺项检出，非错误） |
| 门禁 | `gen_rulesets/cases/synthetic --check`、`check_literals --selftest`、`check_literals` | 全 0；冻结产物逐字节一致 |
| 脱敏 | `audit_sensitive --only dist`（指定产物目录） | 244 文件 0 命中 |
| GUI | `QT_QPA_PLATFORM=offscreen OHSCHECK_GUI_SMOKE=1 ohscheck gui` | exit 0 |
| **同 extras 收集数一致** | 主仓 vs 干净树 `selfcheck --json` | 2025 版 97 因素 / 22 input_required / 90 pending；2014 版 81 / 0 / 486——**两环境逐数一致** |

发现的 L-1/L-2（干净环境才暴露的测试环境耦合）见 §3.1，均已修复并回到干净树复验。

## 八、发布链实测（M6-3～M6-7，2026-10-14，用户批准后执行）

| # | 步骤 | 结果 |
|---|---|---|
| M6-3 | 仓库创建 + 首推 | `gh repo create occupational-health-surveillance-checker --public`（origin: https://github.com/yuluo554/occupational-health-surveillance-checker）→ `git push -u origin main` → **CI 首推四矩阵一次全绿**（run 38522466770：py3.8/py3.12 × ubuntu/windows 全 ✓，1m08s；注记仅 Node 20 弃用提醒，非阻塞） |
| M6-4 | tag + Release | `git tag -a v0.1.0`（锚提交 97410a5）+ push → `gh release create v0.1.0` 附 ASCII 名 zip，notes 含 sha256 与自检说明 |
| M6-5 | 附件可复跑 | zip 244 文件、`ZipInfo(date_time=(2026,10,14,0,0,0))` 固定时间戳 + `create_system=0` + 固定 external_attr；**同参数再生成两次 sha256 逐字节一致**（`703d1e3f…728ab`，49,009,569 B）；`sha256sums.txt` 对账 OK |
| M6-6 | 真下载回验 | `gh release download` 真下载 → sha256 对账一致 → 中立目录解压 → `ohscheck-cli.exe selftest` exit 0（`frozen=true / data_dir_inside_exe=true / engine_ok=true / bench_ok=true / ok=true`）；剥 PATH（只留 System32）CLI version + GUI offscreen 冒烟双 exit 0 |
| M6-7 | 同基线 | 冻结产物构建于 M5 提交 24e8c1c；`git diff 24e8c1c..HEAD -- src/ tools/packaging.spec` 为空（0 改动）→ 发布源码与产物同基线成立；`--selftest` 在发布提交上复跑 exit 0 |

发布后本地门禁复跑：双通道 pytest、全部 `--check`、selfcheck/bench、audit 四步全绿（CI 同步背书）。

## 九、诚实性终态

- CI 徽章自首推起反映真实运行状态（首跑全绿）。
- git 历史含 QQ 邮箱提交身份（§五 决策：不改写）；后续提交建议 `yuluo554@users.noreply.github.com`。
- plan/ 内个人标识按 §六 新口径**逐文件扫描**（2026-10-19 起代码已收口，命中 0）；发布源码 zip 含 plan/ 按 §六 接受；dist zip 不含 plan/。

## 十、v0.1.1 本地构建记录（2026-10-19；**未发布**）

> 迭代 v0.1.1（脱敏口径收口 / 示例入仓 / floor 抬 3.12 / 顶层 status 纳入校验）只做**本地构建与验收**；
> tag `v0.1.1` 与 `gh release create` 属对外动作，由用户本人执行（2FA）。本节数字为本地实测，**发布后须以下载件复算为准**。

| 项 | 实测 |
|---|---|
| 构建 | `py -3.12 -m PyInstaller tools/packaging.spec`（PyInstaller 6.22.3 / PySide6 6.12.0 / Python 3.12.10），`gen_spec --check` 先行 OK |
| 产物 | `dist/ohscheck/` **256 文件**；`_internal/data/` 82 项（rules 3 + benchmark 5 + truth 74）；**无 `knowledge/`、无 `plan/`** |
| 冻结自检 | `ohscheck-cli.exe selftest` rc 0：`frozen=True`、`data_dir_inside_exe=True`、`engine_ok=True`、`bench_ok=True`、`bench_exit_code=0`；`selfcheck` / `bench` rc 0 |
| zip（ASCII 名） | `ohscheck-0.1.1-win64.zip` **256 条目 / 128,791,986 B**，`date_time=(2026,10,19,0,0,0)` + `create_system=0` + 固定 `external_attr`；**同参数再生成两次 sha256 逐字节一致** |
| zip sha256 | `70e11b4164ee7006848844325155c23bc6ebd4439e07d00b3f1672e449f9957f` |
| 解压复验 | 解压后 `ohscheck-cli.exe selftest` rc 0（四项 True）+ `bench` rc 0 + `selfcheck` rc 0 |
| 产物脱敏 | `audit_sensitive --dist-dir dist/ohscheck`：扫描 256 个产物文件，第三方官方路径豁免 64 处，本项目产物命中 0 |

> 体积从 v0.1.0 的 49,009,569 B 增至 128,791,986 B，原因是 `gui` 依赖由 PySide6 6.6.3.1 升到 **6.12.0**（迭代 D-3 移除 3.8 专用上界）。

