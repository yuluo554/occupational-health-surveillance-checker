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
| step1 tree | 工作树全部**已跟踪文件**（`git ls-files`；`plan/` 目录按 HANDOFF-M6 §五口径豁免） | 0 命中 | `py -3.8 -X utf8 tools/audit_sensitive.py` |
| step2 history | git **全量历史**逐提交 grep（`fetch-depth: 0` 保证不空转，D-40；提交数 0 = 空转失败） | 0 命中 | 同上（单步：`--only history`） |
| step3 dist | **产物本体**二进制扫描（构建目录逐文件字节级） | 本项目自有产物 0 命中；第三方官方路径豁免逐条显式列出 | 同上（单步：`--only dist --dist-dir <目录>`） |
| step4 meta | git 作者/提交者身份清单 | informational（恒通过）——发布身份取舍属对外动作，由发布者显式决策 | 同上（单步：`--only meta`） |

阳性对照（任何"0 命中"结论必须先跑，D-27 同族）：

```bash
py -3.8 -X utf8 tools/audit_sensitive.py --selftest
# → AUDIT_SELFTEST_OK: 文本 token 全报出（identity_number,machine_path,username,users_home），
#   干净对照 0 命中，二进制官方路径豁免 0 误报、盘符根泄漏报出 1 处
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
    yuluo554 <yuluo554@users.noreply.github.com> | committer: yuluo554 <yuluo554@users.noreply.github.com>
→ exit 0
```

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

git 历史存在两种作者身份：`yuluo554 <yuluo554@users.noreply.github.com>`（多数提交）与 `yuluo554 <yuluo554@users.noreply.github.com>`（2 提交）。

- **历史不改写**：QQ 邮箱仅存在于提交**元数据**，从未出现在文件内容（step2 全历史 0 命中背书）；改写全部历史会使 M6-7"产物与发布源码同基线"与既有 sha256 留档失效，收益（隐藏一个可反查的邮箱）不抵成本。
- **对外动作前的显式决策**：push/tag/release 属 M6-3/M6-4 需用户确认的对外动作；确认时须一并确认 `user.email` 配置——**建议后续提交改用 `yuluo554@users.noreply.github.com`**（GitHub 私有邮箱保护），已用 QQ 邮箱的历史提交按上一条不改写。

## 六、plan/ 豁免口径说明

HANDOFF 快照（`plan/HANDOFF-M1…M6.md`）含本机路径**示例**（"临时目录用仓库树外的 Windows 路径"句式）。这些是写给续接者的环境坑记录，属计划文档；HANDOFF-M6 §五 的发布判据是"发布 zip 内不得出现 **`plan/` 之外**的本地路径泄漏"。故 step1/step2 对 `plan/` 整目录豁免，豁免口径是**目录级整段豁免**（不是逐行放行），写在扫描器常量 `PLAN_EXCLUDE`。

发布源码 zip（M6-5）含 `plan/` 时按本节口径接受；dist 产物 zip 不含 `plan/`，不受影响。
